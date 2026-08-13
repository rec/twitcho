from pathlib import Path

from reccy import rpc

from twitcho.config import Twitcho
from twitcho.control import ControlController, RuntimeState, handle_request


def test_status_request_returns_runtime_snapshot() -> None:
    state = RuntimeState()
    state.set_state("streaming")
    state.set_ffmpeg(alive=True)
    controller = ControlController(state=state)

    response = handle_request(
        controller,
        rpc.Request(id="status-1", command="status"),
    )

    assert response.ok
    assert response.result["status"] == state.snapshot()


def test_mute_and_unmute_requests_change_runtime_state() -> None:
    state = RuntimeState()
    state.set_state("streaming")
    controller = ControlController(state=state)

    handle_request(controller, rpc.Request(id="mute-1", command="mute"))
    assert state.snapshot()["muted"] is True
    handle_request(controller, rpc.Request(id="unmute-1", command="unmute"))
    assert state.snapshot()["muted"] is False


def test_stop_request_is_queued() -> None:
    controller = ControlController(state=RuntimeState())

    response = handle_request(controller, rpc.Request(id="stop-1", command="stop"))

    assert response.ok
    assert controller.commands.get_nowait().name == "stop"


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
