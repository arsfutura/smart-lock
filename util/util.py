import rx
import time
import datetime
import requests


def current_timestamp():
    # Calculate the offset taking into account daylight saving time
    utc_offset_sec = time.altzone if time.localtime().tm_isdst else time.timezone
    utc_offset = datetime.timedelta(seconds=-utc_offset_sec)
    return datetime.datetime.now().replace(tzinfo=datetime.timezone(offset=utc_offset)).replace(
        microsecond=0).isoformat(' ')


def rx_request(method, url,  **kwargs):
    def subscribe(observer, scheduler):
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            observer.on_next(response)
            observer.on_completed()
        except Exception as e:
            observer.on_error(e)

    return rx.create(subscribe)
