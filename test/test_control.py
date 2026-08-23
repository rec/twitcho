from pathlib import Path

from reccy import ipc, rpc

from twitcho.config import Twitcho
from twitcho.control import (
    ControlController,
    RuntimeState,
)


def test_status_request_returns_runtime_snapshot() -> None:
    state = RuntimeState()
    state.set_state("streaming")
    state.set_ffmpeg(alive=True)
    controller = ControlController(state=state)

    response = controller.handle_request(rpc.Request(command="status"))

    assert response == state.snapshot()


def test_mute_and_unmute_requests_change_runtime_state() -> None:
    state = RuntimeState()
    state.set_state("streaming")
    controller = ControlController(state=state)

    assert controller.handle_request(rpc.Request(command="mute")) == "ok"
    assert state.snapshot()["muted"] is True
    assert controller.handle_request(rpc.Request(command="unmute")) == "ok"
    assert state.snapshot()["muted"] is False


def test_stop_request_is_queued() -> None:
    controller = ControlController(state=RuntimeState())

    response = controller.handle_request(rpc.Request(command="stop"))

    assert response == "ok"
    assert controller.commands.get_nowait().name == "stop"


def test_unknown_request_returns_rpc_error() -> None:
    controller = ControlController(state=RuntimeState())

    response = controller.handle_request(rpc.Request(command="missing"))

    assert response == ipc.Error(type="error", message="unknown command missing")


def test_daemon_uses_standard_reccy_control_path() -> None:
    twitcho = Twitcho.model_construct(home=Path("/tmp/twitcho-home"))

    assert twitcho.control_endpoint == Path(
        "/tmp/twitcho-home/.local/state/twitcho/gui.sock"
    )
