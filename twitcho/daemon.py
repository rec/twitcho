from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar, Literal

import tyro
from pydantic import BaseModel, PrivateAttr
from reccy import ipc, models, rpc, service, service_spec
from reccy.reccy import Reccy, ReccyStatus

from . import control, streamer
from .config import Twitcho
from .twitch_api import TwitchApi

TWITCHO_SERVICE = service_spec.load(Path(__file__).with_name("service.toml"))


class DaemonOptions(BaseModel, frozen=True):
    action: Annotated[
        Literal["run", "install", "uninstall", "start", "stop", "restart", "status"],
        tyro.conf.Positional,
    ] = "run"
    config: Path = Path.home() / ".config/twitcho/config.json"


class TwitchoDaemon(Reccy, frozen=True):
    service_spec: ClassVar[models.ServiceSpec] = TWITCHO_SERVICE
    status_model: ClassVar[type[ReccyStatus]] = ReccyStatus
    rpc_enabled: ClassVar[bool] = True
    rpc_role: ClassVar[str] = "twitcho"
    logger_name: ClassVar[str] = "twitcho"

    config: Twitcho | None = None

    _controller: control.ControlController | None = PrivateAttr(default=None)

    def run(self) -> int:
        if self.config is None:
            raise ValueError("Twitcho configuration is required")
        controller = control.ControlController(
            state=control.RuntimeState(),
            twitch=TwitchApi.from_config(self.config),
        )
        object.__setattr__(self, "_controller", controller)
        self.start()
        try:
            returncode = streamer.stream(self.config, controller)
        finally:
            self.close()
        if returncode:
            self.publish_error(f"ffmpeg exited with {returncode}")
        return returncode

    def rpc_response(self, request: rpc.Request) -> rpc.Result:
        if self._controller is None:
            return ipc.Error(type="error", message="Twitcho is not running")
        return self._controller.handle_request(request)


def main(argv: list[str] | None = None) -> int:
    options = tyro.cli(DaemonOptions, args=argv)
    return run(options)


def run(options: DaemonOptions) -> int:
    daemon = TwitchoDaemon()
    if options.action == "run":
        config = Twitcho.model_validate_json(options.config.expanduser().read_text())
        return TwitchoDaemon(config=config).run()
    if options.action == "install":
        result = daemon.install_service(
            [
                "-m",
                "twitcho",
                "daemon",
                "run",
                "--config",
                str(options.config.expanduser().resolve()),
            ]
        )
    else:
        result = getattr(daemon, f"{options.action}_service")()
    service.print_service_status(TWITCHO_SERVICE.name, result)
    return 0 if result.running is not False else 1
