import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from twitcho.config import Twitcho
from twitcho.control import (
    ControlController,
    RuntimeState,
    handle_message,
    start_control_server,
    stop_control_server,
)


def _config(port: int = 17_351) -> Twitcho:
    return Twitcho(
        device_name="X18",
        channel=2,
        video=Path("visual-bed.mp4"),
        twitch_key="key",
        control_port=port,
    )


def test_hello_replies_with_server_version() -> None:
    state = RuntimeState()
    controller = ControlController(state=state)

    response = handle_message(
        _config(),
        controller,
        {"type": "hello", "version": 1, "client": "show-control"},
    )

    assert response == {"type": "hello", "version": 1, "server": "twitcho"}


def test_status_command_returns_runtime_snapshot() -> None:
    state = RuntimeState()
    state.set_state("streaming")
    state.set_ffmpeg(alive=True)
    controller = ControlController(state=state)

    response = handle_message(
        _config(),
        controller,
        {"type": "command", "id": "status-1", "command": "status"},
    )

    assert response["type"] == "reply"
    assert response["id"] == "status-1"
    assert response["ok"] is True
    assert response["status"]["state"] == "streaming"
    assert response["status"]["ffmpeg_alive"] is True


def test_mute_and_unmute_commands_change_runtime_state() -> None:
    state = RuntimeState()
    state.set_state("streaming")
    controller = ControlController(state=state)

    handle_message(_config(), controller, {"type": "command", "command": "mute"})
    assert state.snapshot()["muted"] is True
    assert state.snapshot()["state"] == "muted"

    handle_message(_config(), controller, {"type": "command", "command": "unmute"})
    assert state.snapshot()["muted"] is False
    assert state.snapshot()["state"] == "streaming"


def test_stop_command_is_queued() -> None:
    state = RuntimeState()
    controller = ControlController(state=state)

    response = handle_message(
        _config(), controller, {"type": "command", "id": "stop-1", "command": "stop"}
    )

    command = controller.commands.get_nowait()
    assert response == {"type": "reply", "id": "stop-1", "ok": True}
    assert command.name == "stop"
    assert command.message_id == "stop-1"
    assert command.payload == {}


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        (
            "update_stream_info",
            {"title": "Live at the club", "category": "Music", "tags": ["live"]},
        ),
        ("chat", {"message": "Starting now"}),
        ("announce", {"message": "Recording and streaming"}),
        ("clip", {}),
        ("marker", {"description": "First song"}),
    ],
)
def test_show_control_twitch_commands_are_queued(
    command: str, payload: dict[str, object]
) -> None:
    state = RuntimeState()
    controller = ControlController(state=state)
    message = {"type": "command", "id": "action-1", "command": command} | payload

    response = handle_message(_config(), controller, message)

    queued = controller.commands.get_nowait()
    assert response == {"type": "reply", "id": "action-1", "ok": True}
    assert queued.name == command
    assert queued.message_id == "action-1"
    assert queued.payload == payload


def test_unknown_command_fails_without_queueing() -> None:
    state = RuntimeState()
    controller = ControlController(state=state)

    response = handle_message(
        _config(), controller, {"type": "command", "command": "x"}
    )

    assert response["ok"] is False
    assert controller.commands.empty()


def test_socket_server_reports_malformed_json_and_continues() -> None:
    with running_server() as port:
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            reader = client.makefile()
            client.sendall(b"{bad json\n")
            assert json.loads(reader.readline())["type"] == "error"

            client.sendall(b'{"type":"command","id":"p1","command":"ping"}\n')
            assert json.loads(reader.readline()) == {
                "type": "reply",
                "id": "p1",
                "ok": True,
                "reply": "pong",
            }


@contextmanager
def running_server() -> Iterator[int]:
    port = unused_port()
    state = RuntimeState()
    controller = ControlController(state=state)
    server, thread = start_control_server(_config(port), controller)
    try:
        yield port
    finally:
        stop_control_server(server, thread)


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
