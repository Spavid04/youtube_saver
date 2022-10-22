import argparse
import copy
import dataclasses
import datetime
import enum
import io
import json
import os
import shutil
import traceback
import typing
import yt_dlp
from yt_dlp.utils import sanitize_filename

from cookiedump import SUPPORTED_BROWSERS, dumpCookies
import utils


@dataclasses.dataclass()
class Config():
    DownloadDirectory: str
    TemporaryDownloads: str

    SourceUrl: str
    AudioOnly: bool

    Browser: str
    CookiesFile: str

    Noisy: bool
    Aria2c: bool
    RetryFailed: bool
    FfmpegPath: str

def parseArgs() -> typing.Optional[Config]:
    parser = argparse.ArgumentParser(description="Youtube convenient auto saver")

    parser.add_argument("--cookies-from-browser", type=str, required=False, default=None, help="Automatically fetch cookies from a browser.",
                        choices=list(SUPPORTED_BROWSERS.keys()))
    parser.add_argument("--cookies", type=str, required=False, default="cookies.txt", help="Path from where to load cookies.")

    parser.add_argument("--download-directory", type=str, required=False, default=".", help="Download directory.")
    parser.add_argument("--temp-directory", type=str, required=False, default="./__downloading", help="Temporary directory where downloads in progress are stored. Must be different than the download directory, and empty.")
    parser.add_argument("--clear-temp-directory", required=False, default=False, action="store_true", help="Clear the temporary download directory before running. This will delete all its files!")

    parser.add_argument("--audio-only", required=False, default=False, action="store_true", help="Save audio only.")

    parser.add_argument("--noisy", required=False, default=False, action="store_true", help="Don't suppress ytdlp messages.")
    parser.add_argument("--aria2c", required=False, default=False, action="store_true", help="Use aria2c as the external downloader.")
    parser.add_argument("--retry-failed", required=False, default=False, action="store_true", help="Retry failed downloads.")
    parser.add_argument("--ffmpeg-path", type=str, required=False, default=None, help="If ffmpeg is not in PATH, use it from here.")

    parser.add_argument("url", type=str, help="URL to a playlist or single video.")

    try:
        args = parser.parse_args()
    except:
        return None

    if args.download_directory == args.temp_directory:
        raise Exception("Temporary and download directories must be different!")
    if not args.clear_temp_directory and os.path.exists(args.temp_directory) and len(os.listdir(args.temp_directory)):
        raise Exception("Temporary directory is not empty!")

    ffmpegPath = args.ffmpeg_path or shutil.which("ffmpeg")
    if ffmpegPath is None:
        raise Exception("Ffmpeg not found!\nYou can get Windows binaries from here: https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-essentials.7z")

    config = Config(
        DownloadDirectory=os.path.abspath(args.download_directory),
        TemporaryDownloads=os.path.abspath(args.temp_directory),
        SourceUrl=args.url,
        AudioOnly=args.audio_only,
        Browser=args.cookies_from_browser,
        CookiesFile=os.path.abspath(args.cookies),
        Noisy=args.noisy,
        Aria2c=args.aria2c,
        RetryFailed=args.retry_failed,
        FfmpegPath=os.path.abspath(ffmpegPath)
    )

    return config


# youtube-dl --merge-output-format mp4 --format bestvideo+bestaudio --external-downloader aria2c
# --external-downloader-args "--file-allocation=none" --no-mtime --embed-thumbnail --add-metadata --all-subs
# --embed-subs --cookies "%cookiefile%" %*

# -f bestaudio --extract-audio --audio-quality 0 --audio-format opus --no-mtime --embed-thumbnail --embed-metadata

class State(enum.Enum):
    Unprocessed = 0
    OK = 1
    Failed = 2

@dataclasses.dataclass()
class Entry():
    id: str
    duration: float
    title: str
    uploader: str
    url: str

    filesize: float = 0
    uploadDate: datetime.date = None
    raw_data: dict = None
    state: State = None


def setStatus(download_dir: str, id: str, title: str, status: str, extra: typing.Optional[typing.Union[str, typing.TextIO]] = None):
    path = os.path.join(download_dir, f"[{status}] - {sanitize_filename(title)} [{id}].txt")
    with open(path, "w") as f:
        if extra:
            if isinstance(extra, str):
                f.write(extra)
            elif isinstance(extra, io.StringIO):
                f.write(extra.read())

def setStatusEx(download_dir: str, id: str, title: str, status: str, exceptions: typing.Optional[typing.List[Exception]], raw_data: typing.Optional[dict]):
    with io.StringIO() as extraInfo:
        if exceptions:
            extraInfo.write("Exceptions:\n")
            for e in exceptions:
                extraInfo.write("======\n")
                extraInfo.write("\n".join(traceback.format_exception(e)) + "\n")
                extraInfo.write("======\n")
            extraInfo.write("\n\n")

        if raw_data:
            extraInfo.write("Raw info:\n")
            extraInfo.write(json.dumps(raw_data))

        extraInfo.seek(0)
        setStatus(download_dir, id, title, status, extraInfo)

def GetState(download_dir: str, id: str) -> State:
    matches = [x for x in os.listdir(download_dir) if id in x]

    if len(matches) == 0:
        return State.Unprocessed
    if len(matches) > 1:
        raise Exception("Invalid state for id %s" % id)

    if matches[0].endswith(".txt"):
        return State.Failed
    else:
        return State.OK

def DeleteFailure(download_dir: str, id: str):
    matches = [x for x in os.listdir(download_dir) if x.endswith(".txt") and id in x]

    if len(matches) == 0:
        return
    if len(matches) > 1:
        raise Exception("Invalid state for id %s" % id)

    os.remove(os.path.join(download_dir, matches[0]))

@dataclasses.dataclass()
class NewEntriesResult():
    TotalIds: int = 0
    HasSeen: int = 0
    FailuresToRetry: typing.List[str] = None
    NewEntries: typing.Generator[Entry, None, None] = None
def fetchNewEntries(cookiesfile: str, url: str, config: Config) -> NewEntriesResult:
    options = {
        "cookiefile": cookiesfile
    }
    newEntries = list()
    failuresToRetry = list()
    result = NewEntriesResult()
    result.FailuresToRetry = failuresToRetry

    durationLambda = lambda d: d["duration"] if "duration" in d else 0

    with yt_dlp.YoutubeDL(options) as ytdl:
        info = ytdl.extract_info(url, download=False, process=False)
        for i in info["entries"]:
            id = i["id"]
            result.TotalIds += 1

            state = GetState(config.DownloadDirectory, id)
            if state == State.OK or (state == State.Failed and not config.RetryFailed):
                result.HasSeen += 1
                continue
            elif state == State.Failed:
                failuresToRetry.append(id)

            entry = Entry(id=id, duration=durationLambda(i), title=i["title"], uploader=i["uploader"], url=i["url"], raw_data=i, state=state)
            newEntries.append(entry)

    newEntries.sort(key=lambda x: x.duration or -1)

    def __fetchGenerator():
        with yt_dlp.YoutubeDL(options) as ytdl:
            for entry in newEntries:
                try:
                    info = ytdl.extract_info(entry.url, download=False)
                except Exception as e:
                    setStatusEx(config.DownloadDirectory, entry.id, entry.title, "failed", [e], entry.raw_data)
                    continue

                if entry.duration is None or entry.duration == -1:
                    setStatusEx(config.DownloadDirectory, entry.id, entry.title, "invalid-duration", None,
                                entry.raw_data)
                    continue

                entry.filesize = info.get("filesize_approx")
                entry.uploadDate = utils.parseDateString(info["upload_date"])
                entry.raw_data = info

                yield entry

    result.NewEntries = __fetchGenerator()
    return result

def getYtdlInstances_video(config: Config) -> typing.List[yt_dlp.YoutubeDL]:
    options = {
        "cookiefile": config.CookiesFile,
        "format": "bestvideo+bestaudio",
        "merge_output_format": "mkv",
        "updatetime": False,
        "embedsubtitles": True,
        "allsubtitles": True,
        "embedthumbnail": True,
        "addmetadata": True,
        "embed_infojson": True,
        "postprocessors": [{"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False},
                           {"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True,
                            "add_infojson": "if_exists"}, {"key": "EmbedThumbnail", "already_have_thumbnail": False},
                           {"key": "FFmpegConcat", "only_multi_video": True, "when": "playlist"}]
    }
    if config.Aria2c:
        options["external_downloader"] = {"default": "aria2c"}
        options["external_downloader_args"] = {"default": ["--file-allocation=none"]}
    if not config.Noisy:
        options["quiet"] = True

    options_fallback = copy.copy(options)
    options_fallback["format"] = "bestvideo[ext=mp4]+bestaudio"

    return [yt_dlp.YoutubeDL(options), yt_dlp.YoutubeDL(options_fallback)]

def getYtdlInstances_audio(config: Config) -> typing.List[yt_dlp.YoutubeDL]:
    options = {
        "cookiefile": config.CookiesFile,
        "format": "bestaudio",
        "merge_output_format": "ogg",
        "extractaudio": True,
        "audioquality": "0",
        "updatetime": False,
        "embedthumbnail": True,
        "addmetadata": True,
        "postprocessors": [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'opus', 'preferredquality': '0', 'nopostoverwrites': False},
            {'key': 'FFmpegMetadata', 'add_chapters': True, 'add_metadata': True, 'add_infojson': 'if_exists'},
            {'key': 'EmbedThumbnail', 'already_have_thumbnail': False},
            {'key': 'FFmpegConcat', 'only_multi_video': True, 'when': 'playlist'}]
    }
    if config.Aria2c:
        options["external_downloader"] = {"default": "aria2c"}
        options["external_downloader_args"] = {"default": ["--file-allocation=none"]}
    if not config.Noisy:
        options["quiet"] = True

    return [yt_dlp.YoutubeDL(options)]

def downloadUrl(ytdl: yt_dlp.YoutubeDL, url: str) -> bool:
    retriesLeft = 5
    while retriesLeft > 0:
        result = ytdl.download([url])
        if result == 0:
            return True
        retriesLeft -= 1
    return False

def download(config: Config):
    os.chdir(config.TemporaryDownloads)

    result = fetchNewEntries(config.CookiesFile, config.SourceUrl, config)

    total = result.TotalIds - result.HasSeen

    print(f"Total videos: {result.TotalIds}")
    print(f"Unprocessed videos: {total}")

    if result.FailuresToRetry:
        for id in result.FailuresToRetry:
            DeleteFailure(config.DownloadDirectory, id)

    if config.AudioOnly:
        ytdls = getYtdlInstances_audio(config)
    else:
        ytdls = getYtdlInstances_video(config)

    progress = 0
    for entry in result.NewEntries:
        success = False
        exceptions = list()

        print(f"Downloading: {entry.title}")

        for ytdl in ytdls:
            try:
                success = downloadUrl(ytdl, entry.url)
                break
            except Exception as e:
                exceptions.append(e)
                utils.clearDir(config.TemporaryDownloads)

        progress += 1

        if success:
            files = os.listdir(config.TemporaryDownloads)
            assert len(files) == 1
            file = files[0]

            if config.AudioOnly:
                # files are in ogg format, but with .opus extension; rename
                newFile = os.path.splitext(file)[0] + ".ogg"
            else:
                newFile = file

            shutil.move(os.path.join(config.TemporaryDownloads, file), os.path.join(config.DownloadDirectory, newFile))
        else:
            utils.clearDir(config.TemporaryDownloads)
            setStatusEx(config.DownloadDirectory, entry.id, entry.title, "failed", exceptions, entry.raw_data)

        if progress % 10 == 0:
            print(f"Progress:\t{progress}\t{total}")

# "https://www.youtube.com/playlist?list=LL"
# "https://music.youtube.com/playlist?list=LM"

def main():
    config = parseArgs()

    if config is None:
        # parsing failed, print some "custom" help

        print()
        print()
        print()
        print("Some simple examples:")
        print()
        print("Download all liked videos, with certain options:")
        print(r'''.\main.py --cookies-from-browser "chrome" --cookies "cookies.txt" --download-directory ".\ytdls" --temp-directory ".\__downloading" --clear-temp-directory --aria2c "https://www.youtube.com/playlist?list=LL"''')
        print()
        print("Download all liked songs, as indexed by youtube music, as audio only:")
        print(r'''.\main.py --cookies-from-browser "chrome" --cookies "cookies.txt" --download-directory ".\ytdls\music" --temp-directory ".\__downloading" --clear-temp-directory --audio-only --aria2c "https://music.youtube.com/playlist?list=LM"''')

        return -1

    if not os.path.isdir(config.DownloadDirectory):
        os.mkdir(config.DownloadDirectory)

    if not os.path.isdir(config.TemporaryDownloads):
        os.mkdir(config.TemporaryDownloads)
    utils.clearDir(config.TemporaryDownloads)

    if config.Browser is not None:
        dumpCookies("youtube.com", config.CookiesFile, browser=config.Browser)

    download(config)

    if config.Browser is not None:
        os.remove(config.CookiesFile)

    return 0

if __name__ == "__main__":
    exit(main())
