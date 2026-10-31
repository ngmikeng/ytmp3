"""Thin wrapper around yt-dlp that downloads audio as MP3 or video as MP4."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from yt_dlp import YoutubeDL, parse_options
from yt_dlp.postprocessor.metadataparser import MetadataParserPP
from yt_dlp.utils import DownloadError

QUALITIES = ("128", "192", "256", "320")
RESOLUTIONS = ("360", "480", "720", "1080", "1440", "2160", "best")
RETRIES = {"retries": 10, "fragment_retries": 10, "file_access_retries": 3, "extractor_retries": 3}

# Playlist entries go in "<playlist title>/NNN - <title> [id].<ext>"; single videos are flat.
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


def _progress_hook(ext: str):
    step = "merging into mp4" if ext == "mp4" else f"converting to {ext}"

    def hook(d: dict) -> None:
        if d["status"] == "finished":
            name = Path(d.get("filename", "")).name
            print(f"  downloaded: {name} -> {step}...", file=sys.stderr)

    return hook


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
    video: bool = False,
    resolution: str = "1080",
) -> dict:
    if quality not in QUALITIES:
        raise ValueError(f"quality must be one of {', '.join(QUALITIES)}")
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {', '.join(RESOLUTIONS)}")
    cookies_spec = parse_browser_spec(cookies_from_browser) if cookies_from_browser else None
    ext = "mp4" if video else "mp3"

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
    if video:
        # Merged downloads already end up as mp4; this catches a single-file (e.g. webm) fallback.
        postprocessors.append({"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"})
    else:
        postprocessors.append({"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality})
    if metadata:
        postprocessors += [
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ]

    if video:
        # Highest resolution up to the cap; at that resolution prefer H.264/AAC, which every player handles.
        sort = ([] if resolution == "best" else [f"res:{resolution}"]) + ["vcodec:h264", "acodec:aac"]
        format_opts = {"format": "bv*+ba/b", "format_sort": sort, "merge_output_format": "mp4"}
    else:
        format_opts = {"format": "bestaudio/best"}

    opts: dict = {
        **format_opts,
        "outtmpl": str(output_dir / OUTPUT_TEMPLATE),
        "allow_playlist_files": False,  # no playlist-level thumbnail/description files
        "postprocessors": postprocessors,
        "writethumbnail": metadata,
        "noplaylist": not playlist,
        "ignoreerrors": "only_download" if playlist else False,
        "overwrites": overwrite,
        # yt-dlp's CLI defaults. Through the Python API these are unset, which means *no* retries,
        # so a single stalled read (common with large video streams) would fail the whole video.
        **RETRIES,
        "windowsfilenames": True,  # Windows-safe names on every OS
        "logger": _Logger(verbose),
        "noprogress": not verbose,
        "progress_hooks": [] if verbose else [_progress_hook(ext)],
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


ON_EXISTS = ("ask", "skip", "overwrite")
_ANSWERS = {"y": "overwrite", "yes": "overwrite", "n": "skip", "no": "skip", "": "skip",
            "a": "overwrite all", "all": "overwrite all", "s": "skip all", "skip all": "skip all"}


def _ask(name: str) -> str:
    """'overwrite' | 'skip' | 'overwrite all' | 'skip all'. EOF (no one to answer) means skip."""
    print(f"  already exists: {name}", file=sys.stderr)
    while True:
        print("  overwrite? [y]es / [N]o / [a]ll / [s]kip all: ", end="", file=sys.stderr, flush=True)
        try:
            answer = input().strip().lower()
        except EOFError:
            print(file=sys.stderr)
            return "skip"
        if answer in _ANSWERS:
            return _ANSWERS[answer]


def _existing_filter(ydl: YoutubeDL, on_exists: str, ask=_ask, ext: str = "mp3"):
    """yt-dlp's overwrites=False only looks for the downloaded file(s) (.webm, ...), which are deleted after the
    conversion/merge, so it would download and process again. Check for the final .<ext> before downloading
    instead, and skip it or ask (overwriting it is what happens when the filter lets the video through)."""
    mode = on_exists

    def match(info: dict, *, incomplete: bool = False) -> str | None:
        nonlocal mode
        if incomplete or not info.get("ext"):
            return None
        final = Path(ydl.prepare_filename(info)).with_suffix(f".{ext}")
        if not final.is_file() or mode == "overwrite":
            return None
        choice = ask(final.name) if mode == "ask" else "skip"
        if choice.endswith(" all"):
            mode = choice.removesuffix(" all")
            choice = mode
        if choice == "overwrite":
            print(f"  overwriting: {final.name}", file=sys.stderr)
            return None
        print(f"  skipped (already exists): {final.name}", file=sys.stderr)
        return f"{final.name} already exists"

    return match


def download(urls: list[str], opts: dict, on_exists: str = "skip", ext: str = "mp3") -> Result:
    """on_exists: what to do when the final .<ext> file is already there ('ask', 'skip', or 'overwrite')."""
    if on_exists not in ON_EXISTS:
        raise ValueError(f"on_exists must be one of {', '.join(ON_EXISTS)}")
    if opts.get("overwrites"):
        on_exists = "overwrite"
    result = Result()
    logger: _Logger = opts["logger"]
    with YoutubeDL(opts) as ydl:
        if on_exists != "overwrite":
            ydl.params["match_filter"] = _existing_filter(ydl, on_exists, ext=ext)
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

