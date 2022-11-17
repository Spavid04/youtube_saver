### Fetch new youtube liked videos
```
main.py --cookies-from-browser "firefox" --cookies "cookies.txt" --download-directory "youtube_likes" --temp-directory "__downloading" --clear-temp-directory "https://www.youtube.com/playlist?list=LL"
```

### Fetch new youtube liked songs (also including videos marked as being a song)
```
main.py --cookies-from-browser "firefox" --cookies "cookies.txt" --download-directory "youtube_music" --temp-directory "__downloading" --clear-temp-directory --audio-only "https://music.youtube.com/playlist?list=LM"
```

### Other stuff
* probably supports many things that yt-dlp itself supports (eg. soundcloud likes)
* pass `--aria2c` to use aria2 for downloading, if you have it in your PATH
