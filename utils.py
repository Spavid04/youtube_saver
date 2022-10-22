import datetime
import os
import time


def clearDir(path: str, retries: int = 5):
    if os.path.isdir(path):
        while retries > 0:
            somethingFailed = False

            for file in os.listdir(path):
                try:
                    os.remove(os.path.join(path, file))
                except Exception as e:
                    somethingFailed = True

            if somethingFailed:
                retries -= 1
                time.sleep(5)
            else:
                retries = 0

def parseDateString(string: str) -> datetime.date:
    assert len(string) == 8
    return datetime.date(
        int(string[0:4]),
        int(string[4:6]),
        int(string[6:8])
    )
