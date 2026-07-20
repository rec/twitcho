from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self


class Range(BaseModel):
    begin: float = 0.0
    end: float = float("inf")

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.begin < 0:
            raise ValueError("range begin must be non-negative")
        if self.end < self.begin:
            raise ValueError("range end must not be before begin")
        return self


class AnimationSegment(BaseModel):
    animation: Path
    body: Range = Field(default_factory=Range)
    loop: Range = Field(default_factory=Range)
    loop_count: int = 1

    @field_validator("loop_count")
    @classmethod
    def validate_loop_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("loop_count must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_loop_is_inside_body(self) -> Self:
        if self.loop.begin < self.body.begin:
            raise ValueError("loop begin must be inside body")
        if self.loop.end > self.body.end:
            raise ValueError("loop end must be inside body")
        return self


class Twitcho(BaseModel):
    device_name: str
    channel: int
    segments: dict[str, AnimationSegment]
    twitch_key: str

    twitch_url: str = "rtmp://live.twitch.tv/app"
    sample_rate: int = 48_000
    audio_bitrate: str = "160k"
    video_bitrate: str = "150k"
    video_resolution: str = "640x360"
    video_frame_rate: int = 10

    @field_validator("channel", "sample_rate", "video_frame_rate")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @model_validator(mode="after")
    def validate_segments(self) -> Self:
        if not self.segments:
            raise ValueError("at least one animation segment is required")
        if not self.twitch_key:
            raise ValueError("twitch_key is required")
        return self

    @property
    def required_channels(self) -> int:
        return self.channel + 1

    @property
    def rtmp_url(self) -> str:
        return f"{self.twitch_url.rstrip('/')}/{self.twitch_key}"
