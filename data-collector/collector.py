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
from rx.scheduler import ThreadPoolScheduler
from rx.scheduler.eventloop import AsyncIOThreadSafeScheduler
from rx.disposable import Disposable
from rx import operators as ops
from PIL import Image
from collections import namedtuple
from util.models import Response
from util.util import current_timestamp


def parse_args():
    parser = argparse.ArgumentParser(
        description='Script for collecting images from camera. Image (frame) will be saved if there is person '
                    'recognised on the frame where min_confidence <= person_confidence <= max_confidence',
        add_help=False)
    required = parser.add_argument_group('required arguments')
    optional = parser.add_argument_group('optional arguments')

    required.add_argument('-min', '--min-confidence', type=float, required=True,
                          help='Minimum confidence required for saving the frame. Number from 0 to 1.')
    required.add_argument('-max', '--max-confidence', type=float, required=True,
                          help='Minimum confidence required for saving the frame. Number from 0 to 1.')
    required.add_argument('--camera-url', required=True, help='URL of video stream.')
    required.add_argument('--face-recognition-api-url', required=True, help='URL of face recognition endpoint.')

    optional.add_argument('--fps', type=float, default=2,
                          help='How many frames per second will collector be processing. Default is 2.')
    optional.add_argument('--haar-file-path', default='util/haarcascade_frontalface_default.xml',
                          help='Path to Haar Cascade (simple and fast face detector) xml file')
    optional.add_argument('--log-path', default='log', help='Directory path where logs will be saved.')

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
    img = img.resize((640, 360))  # resize for faster inference
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


def save_frame(img_faces_pair):
    img_faces_pair.img.save(
        '{}/{}-{:.2f}-{}.jpeg'.format(ARGS.log_path, img_faces_pair.faces[0].top_prediction.label,
                                      img_faces_pair.faces[0].top_prediction.confidence, current_timestamp()))


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

    video_stream_observable = rx.using(
        lambda: VideoStreamDisposable(),
        lambda d: rx.from_iterable(video_stream_iterable(d.cap))
    )

    disposable = video_stream_observable.pipe(
        ops.subscribe_on(scheduler),
        ops.sample(1 / ARGS.fps),  # sample frames based on fps
        ops.filter(has_face),  # filter frames without faces
        ops.map(lambda frame: Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))),  # map frame to PIL image
        ops.observe_on(io_scheduler),
        ops.map(lambda img: ImageFacesPair(img, analyse_frame(img))),  # analyse faces on frame
        ops.filter(lambda img_faces_pair: any(
            [
                face.top_prediction.confidence >= ARGS.min_confidence and face.top_prediction.confidence <= ARGS.max_confidence
                for face in img_faces_pair.faces
            ])),  # proceed only if min_confidence <= person_confidence <= max_confidence
        ops.do_action(on_next=save_frame)
    ).subscribe(on_error=lambda e: logger.exception(e))

    try:
        loop.run_forever()
    except Exception as e:
        logger.exception(e)
        logger.info("Data collector shutdown")
        disposable.dispose()


if __name__ == '__main__':
    main()
