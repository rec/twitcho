from pathlib import Path
from unittest import mock

from reccy.services.models import StatusResult

from twitcho import daemon
from twitcho.config import Twitcho


def test_install_creates_daemon_service_with_absolute_config_path() -> None:
    config = Path("private/config.json")
    with (
        mock.patch.object(
            Twitcho,
            "install_service",
            return_value=StatusResult(installed=True, running=True),
        ) as install_service,
        mock.patch("twitcho.daemon.print_service_status"),
    ):
        result = daemon.run(daemon.DaemonOptions(action="install", config=config))

    assert result == 0
    assert install_service.call_args.args == (
        [
            "daemon",
            "run",
            "--config",
            str(config.resolve()),
        ],
    )
