#!/usr/bin/env python

import sys
import argparse
import cv2
import requests
import io
import time
import multiprocessing
import rx
import logging
import asyncio
from pathlib import Path
from rx.subject import Subject
from rx.scheduler import ThreadPoolScheduler
from rx.scheduler.eventloop import AsyncIOThreadSafeScheduler
from rx.disposable import Disposable
from rx import operators as ops
from PIL import Image
from collections import namedtuple
from util.models import Response
from util.util import current_timestamp, rx_request


def parse_args():
    parser = argparse.ArgumentParser(description='Face recognition engine which hooks to camera stream, performs face '
                                                 'recognition on stream frames and sends unlocks door request if a '
                                                 'familiar face is recognised.', add_help=False)
    required = parser.add_argument_group('required arguments')
    optional = parser.add_argument_group('optional arguments')

    required.add_argument('--camera-url', required=True, help='URL of video stream.')
    required.add_argument('--face-recognition-api-url', required=True, help='URL of face recognition endpoint.')
    required.add_argument('--door-api-url', required=True, help='URL of smart lock door-api which unlocks door.')
    required.add_argument('--threshold', type=float, default=0.8, required=True,
                          help='Number from 0 to 1 which represents minimal confidence which need to be met to unlock '
                               'the door when face is recognised from a video stream. Default values is 0.8 (We need '
                               'to be at least 80%% sure that we recognised some person to unlock the door for him).')

    optional.add_argument('--fps', type=float, default=2,
                          help='How many frames per second will engine be processing. This parameter affects engine '
                               'performance the most, setting too high fps can dramatically slow down the engine. '
                               'Default value od 2 should be good enough in most situations.')
    optional.add_argument('--haar-file-path', default='util/haarcascade_frontalface_default.xml',
                          help='Path to Haar Cascade (simple and fast face detector) xml file.')
    optional.add_argument('--log-path', default='log', help='Directory path where logs will be saved. Default is "log".')
    optional.add_argument('--block-time', type=int, default=6,
                          help='After door is unlocked engine will stop processing frame for block-time seconds. By '
                               'default, engine will stop processing frames for 6 seconds after unlock.')

    # Add help
    optional.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                          help='show this help message and exit')
    return parser.parse_args()


ARGS = parse_args()
haar_face_detector = cv2.CascadeClassifier(ARGS.haar_file_path)

ImageFacesPair = namedtuple('ImageFacesPair', 'img faces')

Path('log').mkdir(exist_ok=True)
logger = logging.getLogger()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
fh = logging.FileHandler('{}/log.txt'.format(ARGS.log_path))
fh.setFormatter(formatter)
logger.setLevel(logging.INFO)
logger.addHandler(ch)
logger.addHandler(fh)


def analyse_frame(img):
    logger.info('Analysing frame...')
    start = time.time()

    buffer = io.BytesIO()
    img.save(buffer, 'jpeg')

    logger.info('Firing face recognition request...')
    api_start = time.time()
    try:
        response = requests.post(ARGS.face_recognition_api_url, files={'image': buffer.getvalue()})
        response.raise_for_status()
        logger.info('Face recognition request took {}s'.format(time.time() - api_start))
        logger.info(str(response.content, encoding='utf-8').strip())
        logger.info('Analysis took {}s\n'.format(time.time() - start))
        return Response(response.json()).faces
    except Exception as e:
        logger.error('Error occurred while executing face recognition request!')
        logger.exception(e)
        return []


def log_unlock(img_faces_pair):
    root_dir = Path('{}/unlock-frames/{}'.format(ARGS.log_path, current_timestamp()))
    root_dir.mkdir(parents=True, exist_ok=True)
    img_faces_pair.img.save('{}/frame.jpeg'.format(root_dir.absolute()))
    recognised_people = filter(lambda face: face.top_prediction.confidence > ARGS.threshold, img_faces_pair.faces)
    for face in recognised_people:
        root_dir.joinpath('{}-{}'.format(face.top_prediction.label, face.top_prediction.confidence)).touch()


def unlock_request(img_faces_pair):
    return rx_request('post', ARGS.door_api_url, timeout=0.3).pipe(
        ops.do_action(on_error=lambda e: logger.exception(e)),
        ops.retry(3),
        ops.catch(rx.empty()),
        ops.do_action(on_next=lambda _: logger.info('Door unlocked\n')),
        ops.do_action(on_next=lambda _: log_unlock(img_faces_pair))
    )


def has_face(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = haar_face_detector.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
    return len(faces) > 0


class VideoStreamDisposable(Disposable):
    def __init__(self):
        self.cap = cv2.VideoCapture()
        super().__init__(lambda: self.cap.release())


def video_stream_iterable(cap):
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    while True:
        while not cap.open(ARGS.camera_url):
            logger.error("Cannot open video stream!")
            time.sleep(1)

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            yield frame


def main():
    loop = asyncio.get_event_loop()
    io_scheduler = AsyncIOThreadSafeScheduler(loop=loop)
    scheduler = ThreadPoolScheduler(multiprocessing.cpu_count())

    semaphore = Subject()

    semaphore_stream = semaphore.pipe(
        ops.flat_map(lambda _:
                     rx.of(True).pipe(
                         ops.delay(ARGS.block_time, scheduler=scheduler),
                         ops.start_with(False))
                     ),
        ops.start_with(True)
    )

    video_stream_observable = rx.using(
        lambda: VideoStreamDisposable(),
        lambda d: rx.from_iterable(video_stream_iterable(d.cap))
    )

    gated_video_stream = video_stream_observable.pipe(
        ops.subscribe_on(scheduler),
        ops.sample(1 / ARGS.fps),  # sample frames based on fps
        ops.combine_latest(semaphore_stream),
        ops.filter(lambda tup: tup[1]),  # proceed only if semaphore allows
        ops.map(lambda tup: tup[0])  # take only frame
    )

    disposable = gated_video_stream.pipe(
        ops.filter(has_face),  # filter frames without faces
        ops.map(lambda frame: Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))),  # map frame to PIL image
        ops.map(lambda img: img.resize((640, 360))),  # resize image (inference will be faster)
        ops.observe_on(io_scheduler),
        ops.map(lambda img: ImageFacesPair(img, analyse_frame(img))),  # analyse frame for faces
        ops.filter(lambda img_faces_pair: any(
            [face.top_prediction.confidence > ARGS.threshold for face in img_faces_pair.faces])),  # proceed only if there is a known face in the frame
        ops.throttle_first(1),
        ops.flat_map(unlock_request),  # unlock the door
        ops.do_action(on_next=lambda _: semaphore.on_next(True))  # trigger semaphore which will block stream for "block-seconds" seconds (doors are unlocked for that long after unlock request)
    ).subscribe(on_error=lambda e: logger.exception(e))

    try:
        loop.run_forever()
    except Exception as e:
        logger.exception(e)
        logger.info("Smart lock face recognition engine shutdown")
        disposable.dispose()


if __name__ == '__main__':
    main()
