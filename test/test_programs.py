import subprocess as sp
import sys

import pytest

from twitcho.control import RuntimeState
from twitcho.programs import parse_bitrate, run_silent, update_bitrate


def test_run_silent_hides_successful_output(capsys: pytest.CaptureFixture[str]) -> None:
    run_silent(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr)",
        ]
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_silent_shows_failed_output(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(sp.CalledProcessError):
        run_silent(
            [
                sys.executable,
                "-c",
                "import sys; print('out'); print('err', file=sys.stderr); sys.exit(2)",
            ]
        )

    captured = capsys.readouterr()
    assert "Command failed:" in captured.err
    assert "stdout:" in captured.err
    assert "out" in captured.err
    assert "stderr:" in captured.err
    assert "err" in captured.err


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("124.8kbits/s", 124.8),
        ("300000bits/s", 300.0),
        ("1.2Mbits/s", 1200.0),
        ("N/A", None),
    ],
)
def test_parse_bitrate(value: str, expected: float | None) -> None:
    assert parse_bitrate(value) == expected


def test_update_bitrate_stores_ffmpeg_progress_value() -> None:
    state = RuntimeState()

    update_bitrate(state, "bitrate= 250.5kbits/s\n")

    assert state.snapshot()["output_bitrate_kbps"] == 250.5
