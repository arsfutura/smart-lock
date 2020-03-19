#!/usr/bin/env python

import argparse
import time
import schedule
import threading
from flask import Flask, Response
import RPi.GPIO as GPIO


def parse_args():
    parser = argparse.ArgumentParser('Simple Flask api for unlocking door with electric strike lock connected with '
                                     'Raspberry Pi via GPIO pins.', add_help=False)
    required = parser.add_argument_group('required arguments')
    optional = parser.add_argument_group('optional arguments')

    required.add_argument('-p', '--pin', type=int, required=True,
                          help='Index of GPIO pin (in GPIO.BOARD mode) which controls relay.')
    optional.add_argument('-d', '--lock-delay', type=int, default=3, help='How much time should we activate relay.')

    # Add help
    optional.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS,
                          help='show this help message and exit')
    return parser.parse_args()


ARGS = parse_args()

GPIO.cleanup()
GPIO.setmode(GPIO.BOARD)
GPIO.setup(ARGS.pin, GPIO.OUT, initial=GPIO.HIGH)

app = Flask(__name__)


def lock(): GPIO.output(ARGS.pin, GPIO.HIGH)


def unlock(): GPIO.output(ARGS.pin, GPIO.LOW)


def scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


thread = threading.Thread(target=scheduler, name='Scheduler', daemon=True)
thread.start()


def lock_job():
    lock()
    return schedule.CancelJob


def schedule_lock():
    """
    Cancels current lock job (if exists) and schedules another one for LOCK_DELAY seconds.
    Basically, if there is lock job scheduled, it delays it for another LOCK_DELAY seconds, if there is no lock
    scheduled, it schedules lock in LOCK_DELAY seconds (If we repeatedly get unlock requests, we just delay lock little
    bit more).
    """
    schedule.jobs.clear()  # cancel all jobs
    schedule.every(ARGS.lock_delay).seconds.do(lock_job)  # schedule lock in LOCK_DELAY seconds


@app.route('/unlock', methods=['POST'])
def unlock_route():
    unlock()
    schedule_lock()
    return Response(status=202)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
