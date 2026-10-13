# ytmp3

Download YouTube audio as MP3 from the command line. It needs **no login and no API key**, and runs on **macOS and Windows** (Linux works too).

The tool is a thin wrapper around [yt-dlp](https://github.com/yt-dlp/yt-dlp). Features:

- 128 / 192 / 256 / 320 kbps MP3
- Embedded title/artist/date tags and the thumbnail as cover art
- Playlists: each video is saved as `Playlist Title/001 - Title [id].mp3`
- Batch downloads from a text file
- Zero setup for ffmpeg and the JavaScript runtime. If they aren't installed, a copy is bundled or downloaded on first run.

> For personal use with content you have the right to download. Respect YouTube's Terms of Service and copyright. Only public and unlisted videos are supported.

## Install

You need [uv](https://docs.astral.sh/uv/). It installs Python for you if needed.

**macOS**
```sh
brew install uv
uv tool install /path/to/ytdl-mp3
```

**Windows (PowerShell)**
```powershell
winget install astral-sh.uv
uv tool install C:\path\to\ytdl-mp3
```

After installing, `ytmp3` is available in any new terminal. If it isn't found, run `uv tool update-shell` once.

To run without installing, use `uv run ytmp3 ...` from the project folder.

## Usage

```sh
ytmp3 "https://www.youtube.com/watch?v=jNQXAC9IVRw"                 # single video
ytmp3 "https://youtu.be/jNQXAC9IVRw" -q 320 -o ~/Music              # 320 kbps into ~/Music
ytmp3 "https://www.youtube.com/playlist?list=PL..."                 # whole playlist
ytmp3 "https://www.youtube.com/watch?v=ID&list=PL..." --no-playlist # just that video
ytmp3 -f urls.txt                                                   # batch file
```

Always put URLs in quotes. `&` and `?` are special characters in zsh and PowerShell.

`urls.txt` has one URL per line. Blank lines and lines starting with `#` are ignored, and duplicates are skipped. Files saved from Notepad (UTF-8 with BOM, CRLF line endings) work.

| Option | Description |
|---|---|
| `-f, --file FILE` | Read URLs from a text file (can be combined with URLs on the command line) |
| `-o, --output DIR` | Output directory (default `./downloads`) |
| `-q, --quality` | `128`, `192` (default), `256` or `320` kbps |
| `--no-playlist` | For `watch?v=…&list=…` URLs, download only the video |
| `--no-metadata` | Skip ID3 tags and cover art |
| `--overwrite` | Re-download files that already exist (they are skipped by default) |
| `--ffmpeg PATH` | Use a specific ffmpeg binary or folder |
| `-v, --verbose` | Show full yt-dlp output |

Exit codes: `0` means everything succeeded, `1` means some URLs failed (they are listed in the summary), and `2` means a setup error such as no URLs or no ffmpeg.

## How dependencies are found

- **ffmpeg** (conversion and tagging) is looked up in this order: `--ffmpeg`, then `ffmpeg`/`ffprobe` on `PATH`, then an automatic download through [static-ffmpeg](https://pypi.org/project/static-ffmpeg/). The download happens once and is cached. If you'd rather use a system install, run `brew install ffmpeg` or `winget install Gyan.FFmpeg`.
- **JavaScript runtime** (yt-dlp needs one to solve YouTube's challenges) is looked up in this order: `deno` on `PATH`, then the Deno binary bundled through the `deno` Python package, then `node`, then `bun`.

## When downloads start failing

YouTube changes things often, and a new yt-dlp release almost always fixes it:

```sh
uv tool upgrade ytmp3                                       # installed tool
uv lock --upgrade-package yt-dlp && uv sync                 # dev checkout
```

## Development

```sh
uv sync
uv run pytest
```
