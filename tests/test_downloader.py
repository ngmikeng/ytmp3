from pathlib import Path

import pytest
from yt_dlp import YoutubeDL

from ytmp3.downloader import _ask, _existing_filter, build_opts, download


def _keys(opts):
    return [pp["key"] for pp in opts["postprocessors"]]


def test_defaults(tmp_path: Path):
    opts = build_opts(tmp_path)
    assert opts["format"] == "bestaudio/best"
    assert opts["noplaylist"] is False
    assert opts["writethumbnail"] is True
    assert opts["windowsfilenames"] is True
    extract = next(pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegExtractAudio")
    assert extract == {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
    assert _keys(opts) == ["MetadataParser", "FFmpegThumbnailsConvertor", "FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"]
    assert "cookiefile" not in opts and "cookiesfrombrowser" not in opts


def test_no_metadata(tmp_path: Path):
    opts = build_opts(tmp_path, metadata=False)
    assert _keys(opts) == ["FFmpegExtractAudio"]
    assert opts["writethumbnail"] is False


def test_quality_and_flags(tmp_path: Path):
    opts = build_opts(tmp_path, quality="320", playlist=False, overwrite=True,
                      ffmpeg_dir=tmp_path, js_runtimes={"node": {"path": "/bin/node"}})
    assert next(pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegExtractAudio")["preferredquality"] == "320"
    assert opts["noplaylist"] is True
    assert opts["overwrites"] is True
    assert opts["ffmpeg_location"] == str(tmp_path)
    assert opts["js_runtimes"] == {"node": {"path": "/bin/node"}}


def test_cookies(tmp_path: Path):
    opts = build_opts(tmp_path, cookies_file=tmp_path / "cookies.txt", cookies_from_browser="chrome:Profile 1")
    assert opts["cookiefile"] == str(tmp_path / "cookies.txt")
    assert opts["cookiesfrombrowser"] == ("chrome", "Profile 1", None, None)


def test_invalid_cookies_browser(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported browser"):
        build_opts(tmp_path, cookies_from_browser="netscape")


def test_invalid_quality(tmp_path: Path):
    with pytest.raises(ValueError):
        build_opts(tmp_path, quality="999")


def test_video_defaults(tmp_path: Path):
    opts = build_opts(tmp_path, video=True)
    assert opts["format"] == "bv*+ba/b"
    assert opts["format_sort"] == ["res:1080", "vcodec:h264", "acodec:aac"]
    assert opts["merge_output_format"] == "mp4"
    assert _keys(opts) == ["MetadataParser", "FFmpegThumbnailsConvertor", "FFmpegVideoRemuxer", "FFmpegMetadata", "EmbedThumbnail"]
    assert next(pp for pp in opts["postprocessors"] if pp["key"] == "FFmpegVideoRemuxer")["preferedformat"] == "mp4"


def test_video_best_resolution_and_no_metadata(tmp_path: Path):
    opts = build_opts(tmp_path, video=True, resolution="best", metadata=False)
    assert not any(s.startswith("res:") for s in opts["format_sort"])
    assert _keys(opts) == ["FFmpegVideoRemuxer"]
    assert build_opts(tmp_path, video=True, resolution="720")["format_sort"][0] == "res:720"


def test_audio_mode_has_no_video_options(tmp_path: Path):
    opts = build_opts(tmp_path)
    assert "format_sort" not in opts and "merge_output_format" not in opts


def test_invalid_resolution(tmp_path: Path):
    with pytest.raises(ValueError, match="resolution"):
        build_opts(tmp_path, video=True, resolution="999")


def test_skip_checks_the_final_mp4(tmp_path: Path):
    with YoutubeDL(build_opts(tmp_path, video=True, metadata=False)) as ydl:
        match = _existing_filter(ydl, "skip", ext="mp4")
        info = {"id": "abc", "title": "Clip", "ext": "webm"}
        (tmp_path / "Clip [abc].mp3").write_bytes(b"")  # the audio version doesn't count
        assert match(info) is None
        (tmp_path / "Clip [abc].mp4").write_bytes(b"")
        assert "Clip [abc].mp4 already exists" in match(info)


def _filename(tmp_path: Path, info: dict) -> Path:
    opts = build_opts(tmp_path, metadata=False)
    with YoutubeDL(opts) as ydl:
        return Path(ydl.prepare_filename({"id": "abc", "ext": "webm", **info}))


def test_single_video_filename_is_windows_safe(tmp_path: Path):
    path = _filename(tmp_path, {"title": 'What? A: "test" / ok*'})
    assert path.parent == tmp_path
    assert not set('<>:"/\\|?*') & set(path.name)
    assert path.name.endswith("[abc].webm")


def test_playlist_entry_goes_in_numbered_subfolder(tmp_path: Path):
    path = _filename(tmp_path, {"title": "Song", "playlist_title": "My List", "playlist_index": 7})
    assert path == tmp_path / "My List" / "007 - Song [abc].webm"


def test_long_title_is_truncated_but_keeps_id(tmp_path: Path):
    title = "Lektion 27: STUDIUM UND BERUFE - Việc học tập và nghề nghiệp " * 5
    path = _filename(tmp_path, {"title": title, "playlist_title": "Đức " * 50, "playlist_index": 27})
    assert path.name.endswith(" [abc].webm")
    assert path.name.startswith("027 - Lektion 27")
    assert len(path.parent.name.encode()) <= 80
    assert len(path.name.encode()) <= 160


def test_skip_checks_the_final_mp3(tmp_path: Path):
    with YoutubeDL(build_opts(tmp_path, metadata=False)) as ydl:
        match = _existing_filter(ydl, "skip")
        info = {"id": "abc", "title": "Song v1.2", "ext": "webm"}
        assert match(info) is None
        (tmp_path / "Song v1.2 [abc].mp3").write_bytes(b"")
        assert "already exists" in match(info)
        assert match(info, incomplete=True) is None  # flat playlist entries: not enough info yet
        playlist = {**info, "playlist_title": "My List", "playlist_index": 7}
        assert match(playlist) is None
        (tmp_path / "My List").mkdir()
        (tmp_path / "My List" / "007 - Song v1.2 [abc].mp3").write_bytes(b"")
        assert match(playlist) is not None


def _existing(tmp_path: Path, n: int) -> list[dict]:
    infos = [{"id": f"id{i}", "title": f"Song {i}", "ext": "webm"} for i in range(n)]
    for info in infos:
        (tmp_path / f"{info['title']} [{info['id']}].mp3").write_bytes(b"")
    return infos


def test_ask_per_file_and_for_all(tmp_path: Path):
    infos = _existing(tmp_path, 4)
    answers = iter(["overwrite", "skip", "overwrite all"])
    asked = []

    def ask(name):
        asked.append(name)
        return next(answers)

    with YoutubeDL(build_opts(tmp_path, metadata=False)) as ydl:
        match = _existing_filter(ydl, "ask", ask)
        assert [match(i) is None for i in infos] == [True, False, True, True]  # None = let it download
    assert len(asked) == 3  # "all" stops asking


def test_ask_skip_all(tmp_path: Path):
    infos = _existing(tmp_path, 3)
    with YoutubeDL(build_opts(tmp_path, metadata=False)) as ydl:
        match = _existing_filter(ydl, "ask", lambda name: "skip all")
        assert all(match(i) is not None for i in infos)


@pytest.mark.parametrize("typed, expected", [("y\n", "overwrite"), ("\n", "skip"), ("what\nA\n", "overwrite all"),
                                             ("s\n", "skip all"), ("", "skip")])
def test_ask_answers(monkeypatch, capsys, typed, expected):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(typed))
    assert _ask("x.mp3") == expected
    assert "already exists: x.mp3" in capsys.readouterr().err


def test_overwrite_and_bad_mode(tmp_path: Path):
    with pytest.raises(ValueError):
        download([], build_opts(tmp_path), on_exists="maybe")
