from pathlib import Path

import tyro

from .config import Twitcho
from .streamer import stream


def run(config: Path) -> None:
    stream(Twitcho.model_validate_json(config.read_text()))


def main() -> None:
    tyro.cli(run)


if __name__ == "__main__":
    main()
