from pathlib import Path

import pytest

from ytmp3 import cli
from ytmp3.downloader import Result


def test_read_url_file_handles_bom_crlf_comments(tmp_path: Path):
    f = tmp_path / "urls.txt"
    f.write_bytes(b"\xef\xbb\xbf# header\r\nhttps://a\r\n\r\n  https://b  \r\n#https://c\r\n")
    assert cli.read_url_file(f) == ["https://a", "https://b"]


def test_collect_urls_merges_and_dedupes(tmp_path: Path):
    f = tmp_path / "urls.txt"
    f.write_text("https://b\nhttps://a\n", encoding="utf-8")
    assert cli.collect_urls(["https://a", "https://c"], f) == ["https://a", "https://c", "https://b"]


def test_parser_defaults():
    args = cli.build_parser().parse_args(["https://x"])
    assert args.quality == "192"
    assert args.output == Path("downloads")
    assert not args.no_playlist and not args.no_metadata


def test_parser_video_flags():
    parse = cli.build_parser().parse_args
    args = parse(["https://x"])
    assert args.mp4 is False and args.resolution is None
    args = parse(["https://x", "--mp4", "-r", "720"])
    assert args.mp4 is True and args.resolution == "720"
    with pytest.raises(SystemExit):
        parse(["https://x", "--mp4", "-r", "999"])


def test_main_passes_video_options(monkeypatch, tmp_path: Path):
    seen = {}

    def fake_download(urls, opts, on_exists, ext):
        seen.update(opts=opts, ext=ext)
        return Result()

    monkeypatch.setattr(cli, "resolve_ffmpeg", lambda _: None)
    monkeypatch.setattr(cli, "resolve_js_runtimes", lambda: {})
    monkeypatch.setattr(cli, "download", fake_download)
    assert cli.main(["https://x", "--mp4", "-r", "480", "-o", str(tmp_path)]) == cli.EXIT_OK
    assert seen["ext"] == "mp4"
    assert seen["opts"]["format_sort"][0] == "res:480"


def test_resolution_without_mp4_warns(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(cli, "resolve_ffmpeg", lambda _: None)
    monkeypatch.setattr(cli, "resolve_js_runtimes", lambda: {})
    monkeypatch.setattr(cli, "download", lambda urls, opts, on_exists, ext: Result())
    assert cli.main(["https://x", "-r", "720", "-o", str(tmp_path)]) == cli.EXIT_OK
    assert "only applies with --mp4" in capsys.readouterr().err


def test_parser_rejects_bad_quality():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["https://x", "-q", "999"])


def test_main_without_urls_is_setup_error(capsys):
    assert cli.main([]) == cli.EXIT_SETUP
    assert "no URLs" in capsys.readouterr().err


def test_main_missing_ffmpeg_is_setup_error(monkeypatch, capsys):
    def boom(_):
        raise cli.DependencyError("ffmpeg missing")

    monkeypatch.setattr(cli, "resolve_ffmpeg", boom)
    assert cli.main(["https://x"]) == cli.EXIT_SETUP
    assert "ffmpeg missing" in capsys.readouterr().err


def test_parser_accepts_cookie_flags():
    args = cli.build_parser().parse_args(["https://x", "--cookies-from-browser", "firefox", "--cookies", "c.txt"])
    assert args.cookies_from_browser == "firefox"
    assert args.cookies == Path("c.txt")


def test_main_bad_cookies_browser_is_setup_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "resolve_ffmpeg", lambda _: None)
    assert cli.main(["https://x", "--cookies-from-browser", "netscape"]) == cli.EXIT_SETUP
    assert "unsupported browser" in capsys.readouterr().err


def test_on_exists_mode(monkeypatch):
    import io

    parse = cli.build_parser().parse_args
    assert cli.on_exists_mode(parse(["u", "--overwrite"])) == "overwrite"
    assert cli.on_exists_mode(parse(["u", "--skip-existing"])) == "skip"
    monkeypatch.setattr("sys.stdin", io.StringIO(""))  # not a terminal: nobody to ask
    assert cli.on_exists_mode(parse(["u"])) == "skip"

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr("sys.stdin", Tty(""))
    assert cli.on_exists_mode(parse(["u"])) == "ask"
    with pytest.raises(SystemExit):
        parse(["u", "--overwrite", "--skip-existing"])

