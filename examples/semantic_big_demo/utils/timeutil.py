from datetime import datetime


def current_utc():
    return datetime.utcnow()


def timestamp_utc(epoch):
    return datetime.utcfromtimestamp(epoch)
