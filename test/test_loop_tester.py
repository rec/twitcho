from pathlib import Path

from scripts import loop_tester


def test_preview_command_uses_ffplay_loop_option() -> None:
    command = loop_tester.preview_command(Path("movie-looped.mp4"))

    assert "-loop" in command
    assert "0" == command[command.index("-loop") + 1]
    assert "-stream_loop" not in command
    assert command[-1] == "movie-looped.mp4"


def test_accept_loop_moves_preview_and_original(tmp_path: Path) -> None:
    video = tmp_path / "movie.mp4"
    preview = tmp_path / "preview.mp4"
    video.write_text("original")
    preview.write_text("looped")

    loop_tester.accept_loop(video, preview)

    assert (tmp_path / "movie-looped.mp4").read_text() == "looped"
    assert (tmp_path / "originals" / "movie.mp4").read_text() == "original"
    assert not video.exists()
    assert not preview.exists()


def test_test_loop_skips_on_empty_answer(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "movie.mp4"
    video.write_text("original")
    calls: list[str] = []

    def write_loop(video: Path, preview: Path) -> None:
        preview.touch()

    def play_preview(preview: Path) -> None:
        calls.append("play")

    monkeypatch.setattr(loop_tester, "write_loop", write_loop)
    monkeypatch.setattr(loop_tester, "play_preview", play_preview)
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    loop_tester.test_loop(video)

    assert calls == ["play"]
    assert video.read_text() == "original"
    assert not (tmp_path / "movie-looped.mp4").exists()


def test_test_loop_replays_before_accepting(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "movie.mp4"
    video.write_text("original")
    answers = iter(["r", "l"])
    calls: list[str] = []

    def write_loop(video: Path, preview: Path) -> None:
        preview.touch()

    def play_preview(preview: Path) -> None:
        calls.append("play")

    monkeypatch.setattr(loop_tester, "write_loop", write_loop)
    monkeypatch.setattr(loop_tester, "play_preview", play_preview)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    loop_tester.test_loop(video)

    assert calls == ["play", "play"]
    assert (tmp_path / "movie-looped.mp4").exists()
    assert (tmp_path / "originals" / "movie.mp4").read_text() == "original"
