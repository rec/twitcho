import queue
import threading
import time
from dataclasses import dataclass, field

from reccy import ipc, rpc

from .twitch_api import TwitchApiClient, TwitchApiError


class RuntimeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "starting"
        self.muted = False
        self.ffmpeg_alive = False
        self.ffmpeg_returncode: int | None = None
        self.audio_frames = 0
        self.audio_seconds = 0.0
        self.last_audio_at: float | None = None
        self.left_level_db: float | None = None
        self.right_level_db: float | None = None
        self.clipping = False
        self.output_bitrate_kbps: float | None = None
        self.last_error: str | None = None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self.state,
                "muted": self.muted,
                "ffmpeg_alive": self.ffmpeg_alive,
                "ffmpeg_returncode": self.ffmpeg_returncode,
                "audio_frames": self.audio_frames,
                "audio_seconds": self.audio_seconds,
                "last_audio_at": self.last_audio_at,
                "left_level_db": self.left_level_db,
                "right_level_db": self.right_level_db,
                "clipping": self.clipping,
                "output_bitrate_kbps": self.output_bitrate_kbps,
                "last_error": self.last_error,
            }

    def set_state(self, state: str) -> None:
        with self._lock:
            self.state = state

    def set_error(self, message: str) -> None:
        with self._lock:
            self.state = "failed"
            self.last_error = message

    def set_ffmpeg(self, *, alive: bool, returncode: int | None = None) -> None:
        with self._lock:
            self.ffmpeg_alive = alive
            self.ffmpeg_returncode = returncode

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self.muted = muted
            if self.state in {"streaming", "muted"}:
                self.state = "muted" if muted else "streaming"

    def is_muted(self) -> bool:
        with self._lock:
            return self.muted

    def record_audio(
        self,
        *,
        frames: int,
        sample_rate: int,
        left_level_db: float,
        right_level_db: float,
        clipping: bool,
    ) -> None:
        with self._lock:
            self.audio_frames += frames
            self.audio_seconds = self.audio_frames / sample_rate
            self.last_audio_at = time.time()
            self.left_level_db = left_level_db
            self.right_level_db = right_level_db
            self.clipping = clipping

    def set_output_bitrate(self, bitrate_kbps: float | None) -> None:
        with self._lock:
            self.output_bitrate_kbps = bitrate_kbps


@dataclass
class ControlCommand:
    name: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass
class ControlController:
    state: RuntimeState
    twitch: TwitchApiClient | None = None
    commands: queue.Queue[ControlCommand] = field(default_factory=queue.Queue)

    def handle_request(self, request: rpc.Request) -> rpc.Result:
        command = request.command
        if command == "ping":
            return "pong"
        if command == "status":
            return {"status": self.state.snapshot()}
        if command == "mute":
            self.state.set_muted(True)
            return "ok"
        if command == "unmute":
            self.state.set_muted(False)
            return "ok"
        if command == "stop":
            self.commands.put(ControlCommand(name=command, payload=request.params))
            return "ok"
        if command in TWITCH_API_COMMANDS:
            return self.handle_twitch_command(command, request.params)
        return ipc.Error(type="error", message=f"unknown command {command}")

    def handle_twitch_command(
        self, command: str, payload: dict[str, object]
    ) -> rpc.Result:
        if self.twitch is None:
            return ipc.Error(type="error", message="Twitch API is not configured")
        try:
            return self.twitch.perform(command, payload)
        except TwitchApiError as error:
            return ipc.Error(type="error", message=str(error))


TWITCH_API_COMMANDS = {"update_stream_info", "chat", "announce", "clip", "marker"}
