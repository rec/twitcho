import subprocess as sp
import threading
from collections import deque
from collections.abc import Sequence

from reccy import logging

from .control import RuntimeState

LOGGER = logging.get_logger(__name__)


class OutputTail:
    def __init__(self, line_count: int = 80) -> None:
        self._lines: deque[str] = deque(maxlen=line_count)
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)

    def text(self) -> str:
        with self._lock:
            return "".join(self._lines).strip()


def run_silent(command: Sequence[str], *, text: bool = False) -> sp.CompletedProcess:
    try:
        return sp.run(
            command,
            check=True,
            text=text,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
        )
    except sp.CalledProcessError as error:
        report_failed_command(command, error.stdout, error.stderr)
        raise


def capture_process_stderr(
    process: sp.Popen[bytes], state: RuntimeState | None = None
) -> OutputTail:
    tail = OutputTail()
    if process.stderr is not None:
        thread = threading.Thread(
            target=read_stderr,
            args=(process, tail, state),
            name="TwitchoProcessOutput",
            daemon=True,
        )
        thread.start()
    return tail


def read_stderr(
    process: sp.Popen[bytes], tail: OutputTail, state: RuntimeState | None = None
) -> None:
    assert process.stderr is not None
    for line in process.stderr:
        text = line.decode(errors="replace")
        tail.append(text)
        if state is not None:
            update_bitrate(state, text)


def update_bitrate(state: RuntimeState, line: str) -> None:
    if not line.startswith("bitrate="):
        return
    state.set_output_bitrate(parse_bitrate(line.removeprefix("bitrate=").strip()))


def parse_bitrate(value: str) -> float | None:
    if value == "N/A":
        return None
    if value.endswith("Mbits/s"):
        return float(value.removesuffix("Mbits/s").strip()) * 1000
    if value.endswith("kbits/s"):
        return float(value.removesuffix("kbits/s").strip())
    if value.endswith("bits/s"):
        return float(value.removesuffix("bits/s").strip()) / 1000
    return None


def report_failed_process(command: Sequence[str], tail: OutputTail) -> None:
    report_failed_command(command, None, tail.text())


def report_failed_command(
    command: Sequence[str], stdout: str | bytes | None, stderr: str | bytes | None
) -> None:
    LOGGER.error("Command failed: %s", format_command(command))
    write_output("stdout", stdout)
    write_output("stderr", stderr)


def write_output(label: str, output: str | bytes | None) -> None:
    text = decode_output(output)
    if text:
        LOGGER.error("%s:\n%s", label, text)


def decode_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode(errors="replace").strip()
    return output.strip()


def format_command(command: Sequence[str]) -> str:
    return " ".join(command)
