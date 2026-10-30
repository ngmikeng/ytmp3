"""Thin wrapper around yt-dlp that downloads audio and converts it to MP3."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from yt_dlp import YoutubeDL, parse_options
from yt_dlp.postprocessor.metadataparser import MetadataParserPP
from yt_dlp.utils import DownloadError

QUALITIES = ("128", "192", "256", "320")

# Playlist entries go in "<playlist title>/NNN - <title> [id].mp3"; single videos are flat.
# For single videos the directory part is empty; yt-dlp drops empty segments on Windows
# and "a//b" is equivalent to "a/b" on POSIX.
# Titles are truncated (in UTF-8 bytes) rather than the whole name, so "[id]" is never cut off
# and paths stay well under Windows' 260-char MAX_PATH.
OUTPUT_TEMPLATE = "%(playlist_title|).80B/%(playlist_index&{:03d} - |)s%(title).120B [%(id)s].%(ext)s"


@dataclass
class Result:
    succeeded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)


class _Logger:
    """Routes yt-dlp messages to stderr and remembers the last error for the summary."""

    def __init__(self, verbose: bool):
        self.verbose = verbose
        self.last_error: str | None = None

    def debug(self, msg: str) -> None:
        if self.verbose:
            print(msg, file=sys.stderr)

    info = debug

    def warning(self, msg: str) -> None:
        if self.verbose:
            print(msg, file=sys.stderr)

    def error(self, msg: str) -> None:
        self.last_error = _clean(msg)
        print(msg, file=sys.stderr)


def _progress_hook(d: dict) -> None:
    if d["status"] == "finished":
        name = Path(d.get("filename", "")).name
        print(f"  downloaded: {name} -> converting to mp3...", file=sys.stderr)


def build_opts(
    output_dir: Path,
    quality: str = "192",
    playlist: bool = True,
    metadata: bool = True,
    overwrite: bool = False,
    verbose: bool = False,
    ffmpeg_dir: Path | None = None,
    js_runtimes: dict[str, dict] | None = None,
    cookies_file: Path | None = None,
    cookies_from_browser: str | None = None,
) -> dict:
    if quality not in QUALITIES:
        raise ValueError(f"quality must be one of {', '.join(QUALITIES)}")
    cookies_spec = parse_browser_spec(cookies_from_browser) if cookies_from_browser else None

    # Order mirrors yt-dlp's own CLI: pre_process -> before_dl -> post_process.
    postprocessors: list[dict] = []
    if metadata:
        postprocessors += [
            # Fall back to the channel name when YouTube has no explicit artist.
            {
                "key": "MetadataParser",
                "when": "pre_process",
                "actions": [(MetadataParserPP.Actions.INTERPRET, "%(artist,creator,uploader,channel)s", "%(artist)s")],
            },
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
        ]
    postprocessors.append({"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality})
    if metadata:
        postprocessors += [
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ]

    opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / OUTPUT_TEMPLATE),
        "allow_playlist_files": False,  # no playlist-level thumbnail/description files
        "postprocessors": postprocessors,
        "writethumbnail": metadata,
        "noplaylist": not playlist,
        "ignoreerrors": "only_download" if playlist else False,
        "overwrites": overwrite,
        "windowsfilenames": True,  # Windows-safe names on every OS
        "logger": _Logger(verbose),
        "noprogress": not verbose,
        "progress_hooks": [] if verbose else [_progress_hook],
    }
    if ffmpeg_dir:
        opts["ffmpeg_location"] = str(ffmpeg_dir)
    if js_runtimes:
        opts["js_runtimes"] = js_runtimes
    if cookies_file:
        opts["cookiefile"] = str(cookies_file)
    if cookies_spec:
        opts["cookiesfrombrowser"] = cookies_spec
    return opts


def parse_browser_spec(spec: str) -> tuple:
    """Parse BROWSER[+KEYRING][:PROFILE][::CONTAINER] exactly as yt-dlp's --cookies-from-browser does."""
    try:
        return parse_options(["--cookies-from-browser", spec]).ydl_opts["cookiesfrombrowser"]
    except Exception as e:  # yt-dlp raises OptParseError with a usage banner; keep only the reason
        raise ValueError(str(e).strip().rpartition("error: ")[2]) from None


def download(urls: list[str], opts: dict) -> Result:
    result = Result()
    logger: _Logger = opts["logger"]
    with YoutubeDL(opts) as ydl:
        for url in urls:
            print(f"==> {url}", file=sys.stderr)
            logger.last_error = None
            try:
                ydl.download([url])
            except DownloadError as e:
                result.failed.append((url, logger.last_error or _clean(str(e))))
                continue
            # ydl.download()'s return code is sticky across calls, so rely on the logger instead.
            if logger.last_error:
                result.failed.append((url, logger.last_error))
            else:
                result.succeeded.append(url)
    return result


def _clean(msg: str) -> str:
    return msg.removeprefix("ERROR: ").strip()

