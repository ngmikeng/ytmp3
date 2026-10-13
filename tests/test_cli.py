from pathlib import Path

import pytest

from ytmp3 import cli


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
