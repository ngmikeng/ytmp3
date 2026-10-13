import sys
import types
from pathlib import Path

import pytest

from ytmp3 import deps


def test_explicit_ffmpeg_file_and_dir(tmp_path: Path):
    exe = tmp_path / "ffmpeg.exe"
    exe.write_text("")
    assert deps.resolve_ffmpeg(str(exe)) == tmp_path
    assert deps.resolve_ffmpeg(str(tmp_path)) == tmp_path


def test_explicit_ffmpeg_missing(tmp_path: Path):
    with pytest.raises(deps.DependencyError):
        deps.resolve_ffmpeg(str(tmp_path / "nope"))


def test_ffmpeg_from_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(deps.shutil, "which", lambda name: str(tmp_path / name))
    assert deps.resolve_ffmpeg() == tmp_path


def _fake_static_ffmpeg(monkeypatch, fn):
    run = types.SimpleNamespace(get_or_fetch_platform_executables_else_raise=fn)
    pkg = types.ModuleType("static_ffmpeg")
    pkg.run = run
    monkeypatch.setitem(sys.modules, "static_ffmpeg", pkg)
    monkeypatch.setitem(sys.modules, "static_ffmpeg.run", run)


def test_ffmpeg_falls_back_to_static(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(deps.shutil, "which", lambda name: None)
    _fake_static_ffmpeg(monkeypatch, lambda: (str(tmp_path / "ffmpeg"), str(tmp_path / "ffprobe")))
    assert deps.resolve_ffmpeg() == tmp_path


@pytest.mark.parametrize("platform, hint", [("win32", "winget install Gyan.FFmpeg"), ("darwin", "brew install ffmpeg")])
def test_ffmpeg_unavailable_gives_os_hint(monkeypatch, platform, hint):
    monkeypatch.setattr(deps.shutil, "which", lambda name: None)
    monkeypatch.setattr(deps.sys, "platform", platform)

    def fail():
        raise OSError("offline")

    _fake_static_ffmpeg(monkeypatch, fail)
    with pytest.raises(deps.DependencyError, match=hint):
        deps.resolve_ffmpeg()


def test_js_runtime_prefers_deno_on_path(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda name: f"/bin/{name}")
    assert deps.resolve_js_runtimes() == {"deno": {"path": "/bin/deno"}}


def test_js_runtime_uses_bundled_deno(monkeypatch, tmp_path: Path):
    exe = tmp_path / "deno"
    exe.write_text("")
    monkeypatch.setattr(deps.shutil, "which", lambda name: None)
    monkeypatch.setitem(sys.modules, "deno", types.SimpleNamespace(find_deno_bin=lambda: str(exe)))
    assert deps.resolve_js_runtimes() == {"deno": {"path": str(exe)}}


def test_js_runtime_falls_back_to_node(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda name: "/bin/node" if name == "node" else None)
    monkeypatch.setitem(sys.modules, "deno", None)  # makes `import deno` fail
    assert deps.resolve_js_runtimes() == {"node": {"path": "/bin/node"}}
