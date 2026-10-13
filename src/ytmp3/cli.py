"""Command-line interface: ytmp3 URL [URL ...] [options]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ytmp3 import __version__
from ytmp3.deps import DependencyError, resolve_ffmpeg, resolve_js_runtimes
from ytmp3.downloader import QUALITIES, build_opts, download

EXIT_OK, EXIT_FAILURES, EXIT_SETUP = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ytmp3",
        description="Download YouTube audio as MP3. No login or API key needed.",
    )
    p.add_argument("urls", nargs="*", metavar="URL", help="video or playlist URL(s)")
    p.add_argument("-f", "--file", type=Path, help="text file with one URL per line (# comments allowed)")
    p.add_argument("-o", "--output", type=Path, default=Path("downloads"), help="output directory (default: ./downloads)")
    p.add_argument("-q", "--quality", choices=QUALITIES, default="192", help="MP3 bitrate in kbps (default: 192)")
    p.add_argument("--no-playlist", action="store_true", help="for URLs with both v= and list=, download only the video")
    p.add_argument("--no-metadata", action="store_true", help="skip ID3 tags and cover art")
    p.add_argument("--overwrite", action="store_true", help="overwrite existing files")
    p.add_argument("--ffmpeg", metavar="PATH", help="path to ffmpeg binary or its directory")
    p.add_argument("-v", "--verbose", action="store_true", help="show full yt-dlp output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def read_url_file(path: Path) -> list[str]:
    # utf-8-sig tolerates the BOM Notepad adds; splitlines handles CRLF.
    text = path.read_text(encoding="utf-8-sig")
    return [s for line in text.splitlines() if (s := line.strip()) and not s.startswith("#")]


def collect_urls(cli_urls: list[str], file: Path | None) -> list[str]:
    urls = list(cli_urls)
    if file:
        urls += read_url_file(file)
    return list(dict.fromkeys(urls))  # de-duplicate, keep order


def _utf8_console() -> None:
    # Non-ASCII titles would otherwise crash or garble legacy Windows consoles.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        urls = collect_urls(args.urls, args.file)
    except OSError as e:
        print(f"error: cannot read {args.file}: {e}", file=sys.stderr)
        return EXIT_SETUP
    if not urls:
        parser.print_usage(sys.stderr)
        print("error: no URLs given (pass URLs or --file)", file=sys.stderr)
        return EXIT_SETUP

    try:
        ffmpeg_dir = resolve_ffmpeg(args.ffmpeg)
    except DependencyError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_SETUP

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    opts = build_opts(
        output_dir=output,
        quality=args.quality,
        playlist=not args.no_playlist,
        metadata=not args.no_metadata,
        overwrite=args.overwrite,
        verbose=args.verbose,
        ffmpeg_dir=ffmpeg_dir,
        js_runtimes=resolve_js_runtimes(),
    )
    try:
        result = download(urls, opts)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    print(f"\nDone: {len(result.succeeded)} succeeded, {len(result.failed)} failed. Output: {output}")
    for url, reason in result.failed:
        print(f"  FAILED {url}\n         {reason}")
    return EXIT_FAILURES if result.failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
