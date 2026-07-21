import subprocess as sp
import sys

import pytest

from twitcho.programs import run_silent


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
