"""Locate external binaries (ffmpeg, a JS runtime) in a cross-platform way."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


class DependencyError(RuntimeError):
    """A required external tool could not be found or fetched."""


def _ffmpeg_install_hint() -> str:
    if sys.platform == "win32":
        return "Install it with:  winget install Gyan.FFmpeg   (or pass --ffmpeg PATH)"
    if sys.platform == "darwin":
        return "Install it with:  brew install ffmpeg   (or pass --ffmpeg PATH)"
    return "Install ffmpeg with your package manager (or pass --ffmpeg PATH)"


def _deno_install_hint() -> str:
    if sys.platform == "win32":
        return "winget install DenoLand.Deno"
    if sys.platform == "darwin":
        return "brew install deno"
    return "see https://deno.com"


def resolve_ffmpeg(explicit: str | None = None) -> Path:
    """Return the directory containing ffmpeg and ffprobe.

    Order: explicit path -> system PATH -> static-ffmpeg (auto-download, cached).
    """
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p.parent
        if p.is_dir():
            return p
        raise DependencyError(f"--ffmpeg path does not exist: {p}")

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return Path(ffmpeg).parent

    try:
        from static_ffmpeg import run

        print("ffmpeg not found on PATH; fetching a bundled copy (first run only)...", file=sys.stderr)
        ffmpeg, _ffprobe = run.get_or_fetch_platform_executables_else_raise()
        return Path(ffmpeg).parent
    except Exception as e:  # noqa: BLE001 - any failure here means "unavailable"
        raise DependencyError(f"ffmpeg is required but could not be found or downloaded ({e}).\n{_ffmpeg_install_hint()}") from e


def resolve_js_runtimes() -> dict[str, dict]:
    """Return a yt-dlp ``js_runtimes`` dict, needed to solve YouTube's JS challenges.

    Order: deno on PATH -> bundled deno (PyPI package) -> node -> bun.
    Returns {} if none is available (yt-dlp may still work for some formats).
    """
    if path := shutil.which("deno"):
        return {"deno": {"path": path}}
    try:
        import deno

        path = deno.find_deno_bin()
        if path and Path(path).is_file():
            return {"deno": {"path": str(path)}}
    except Exception:  # noqa: BLE001
        pass
    for name in ("node", "bun"):
        if path := shutil.which(name):
            return {name: {"path": path}}
    print(
        f"warning: no JavaScript runtime found; some videos may fail. Install Deno: {_deno_install_hint()}",
        file=sys.stderr,
    )
    return {}
