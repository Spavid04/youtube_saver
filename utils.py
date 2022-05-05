import datetime
import os


def clearDir(path: str):
    if os.path.isdir(path):
        for file in os.listdir(path):
            os.remove(os.path.join(path, file))

def parseDateString(string: str) -> datetime.date:
    assert len(string) == 8
    return datetime.date(
        int(string[0:4]),
        int(string[4:6]),
        int(string[6:8])
    )
