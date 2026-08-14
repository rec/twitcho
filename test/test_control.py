import tempfile
from pathlib import Path

from reccy import ipc, rpc

from twitcho.config import Twitcho
from twitcho.control import (
    ControlController,
    RuntimeState,
    start_control_server,
    stop_control_server,
)


def test_status_request_returns_runtime_snapshot() -> None:
    state = RuntimeState()
    state.set_state("streaming")
    state.set_ffmpeg(alive=True)
    controller = ControlController(state=state)

    response = controller.handle_request(rpc.Request(command="status"))

    assert response == {"status": state.snapshot()}


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


def test_control_server_returns_simplified_rpc_result() -> None:
    with tempfile.TemporaryDirectory(prefix="twitcho-rpc-", dir="/tmp") as directory:
        config = Twitcho(
            device_name="X18",
            channel=2,
            video=Path("visual-bed.mp4"),
            twitch_key="key",
            home=Path(directory),
        )
        state = RuntimeState()
        state.set_state("streaming")
        controller = ControlController(state=state)
        server = start_control_server(config, controller)
        try:
            response = rpc.Client(config.control_endpoint).call("status")
        finally:
            stop_control_server(server)

        assert response == {"status": state.snapshot()}


def test_control_endpoints_default_to_local_paths() -> None:
    config = Twitcho(
        device_name="X18",
        channel=2,
        video=Path("visual-bed.mp4"),
        twitch_key="key",
        home=Path("/tmp/twitcho-home"),
    )

    assert config.control_endpoint == Path(
        "/tmp/twitcho-home/.local/state/twitcho/control.sock"
    )
    assert config.event_endpoint == Path(
        "/tmp/twitcho-home/.local/state/twitcho/events.sock"
    )
