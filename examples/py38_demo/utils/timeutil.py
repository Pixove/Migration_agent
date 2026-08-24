from datetime import datetime


def current_utc() -> datetime:
    return datetime.utcnow()
