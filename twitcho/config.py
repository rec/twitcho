from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import PrivateAttr, field_validator, model_validator
from reccy import ipc, models, rpc, service_spec
from reccy.reccy import Reccy, ReccyStatus
from typing_extensions import Self

TWITCHO_SERVICE = service_spec.load(Path(__file__).with_name("service.toml"))

if TYPE_CHECKING:
    from .control import ControlController


class Twitcho(Reccy, frozen=True):
    service_spec: ClassVar[models.ServiceSpec] = TWITCHO_SERVICE
    daemon_module: ClassVar[str] = "twitcho"
    status_model: ClassVar[type[ReccyStatus]] = ReccyStatus
    rpc_enabled: ClassVar[bool] = True
    rpc_role: ClassVar[str] = "twitcho"
    logger_name: ClassVar[str] = "twitcho"

    device_name: str
    channel: int
    video: Path
    twitch_key: str
    title_card: Path | None = None

    twitch_url: str = "rtmp://live.twitch.tv/app"
    sample_rate: int = 48_000
    audio_bitrate: str = "160k"
    video_bitrate: str = "150k"
    video_resolution: str = "640x360"
    video_frame_rate: int = 10
    title_interval: float = 180.0
    title_duration: float = 8.0
    title_fade: float = 2.0
    twitch_client_id: str | None = None
    twitch_access_token: str | None = None
    twitch_broadcaster_id: str | None = None
    twitch_sender_id: str | None = None
    twitch_moderator_id: str | None = None
    twitch_api_url: str = "https://api.twitch.tv/helix"

    _controller: "ControlController | None" = PrivateAttr(default=None)

    def run(self) -> int:
        from . import control, streamer
        from .twitch_api import TwitchApi

        controller = control.ControlController(
            state=control.RuntimeState(),
            twitch=TwitchApi.from_config(self),
        )
        object.__setattr__(self, "_controller", controller)
        self.start()
        try:
            returncode = streamer.stream(self, controller)
            if returncode:
                self.publish_error(f"ffmpeg exited with {returncode}")
            return returncode
        finally:
            self.close()

    def rpc_response(self, request: rpc.Request) -> rpc.Result:
        if self._controller is None:
            return ipc.Error(type="error", message="Twitcho is not running")
        return self._controller.handle_request(request)

    @field_validator("channel", "sample_rate", "video_frame_rate")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("title_interval", "title_duration", "title_fade")
    @classmethod
    def validate_nonnegative_title_time(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must not be negative")
        return value

    @model_validator(mode="after")
    def validate_twitch_key(self) -> Self:
        if not self.twitch_key:
            raise ValueError("twitch_key is required")
        return self

    @model_validator(mode="after")
    def validate_title_card(self) -> Self:
        if self.title_card is None:
            return self
        if not self.title_card.exists():
            raise ValueError(f"{self.title_card} does not exist")
        if self.title_interval <= 0:
            raise ValueError("title_interval must be positive")
        if self.title_duration <= 0:
            raise ValueError("title_duration must be positive")
        if self.title_duration >= self.title_interval:
            raise ValueError("title_duration must be shorter than title_interval")
        if self.title_fade * 2 > self.title_duration:
            raise ValueError("title_fade must fit within title_duration")
        return self

    @property
    def required_channels(self) -> int:
        return self.channel + 1

    @property
    def rtmp_url(self) -> str:
        return f"{self.twitch_url.rstrip('/')}/{self.twitch_key}"
