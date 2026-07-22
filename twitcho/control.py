import json
import queue
import socketserver
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

from .config import Twitcho


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


@dataclass
class ControlCommand:
    name: str
    message_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass
class ControlController:
    state: RuntimeState
    commands: queue.Queue[ControlCommand] = field(default_factory=queue.Queue)

    def handle_command(self, message: Mapping[str, object]) -> dict[str, object]:
        command = message.get("command")
        message_id = typed_string(message.get("id"))
        if not isinstance(command, str):
            return {
                "type": "reply",
                "id": message_id,
                "ok": False,
                "error": "missing command",
            }
        if command == "ping":
            return {"type": "reply", "id": message_id, "ok": True, "reply": "pong"}
        if command == "status":
            return {
                "type": "reply",
                "id": message_id,
                "ok": True,
                "status": self.state.snapshot(),
            }
        if command == "mute":
            self.state.set_muted(True)
            return {"type": "reply", "id": message_id, "ok": True}
        if command == "unmute":
            self.state.set_muted(False)
            return {"type": "reply", "id": message_id, "ok": True}
        if command in QUEUED_COMMANDS:
            self.commands.put(
                ControlCommand(
                    name=command,
                    message_id=message_id,
                    payload=command_payload(message),
                )
            )
            return {"type": "reply", "id": message_id, "ok": True}
        return {
            "type": "reply",
            "id": message_id,
            "ok": False,
            "error": f"unknown command {command}",
        }


class ControlServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, config: Twitcho, controller: ControlController) -> None:
        self.config = config
        self.controller = controller
        self.clients: set[ControlHandler] = set()
        self.clients_lock = threading.Lock()
        super().__init__((config.control_host, config.control_port), ControlHandler)

    def add_client(self, client: "ControlHandler") -> None:
        with self.clients_lock:
            self.clients.add(client)

    def remove_client(self, client: "ControlHandler") -> None:
        with self.clients_lock:
            self.clients.discard(client)

    def broadcast(self, message: Mapping[str, object]) -> None:
        with self.clients_lock:
            clients = list(self.clients)
        for client in clients:
            client.write_message(message)


class ControlHandler(socketserver.StreamRequestHandler):
    server: ControlServer

    def setup(self) -> None:
        super().setup()
        self._write_lock = threading.Lock()
        self.server.add_client(self)

    def finish(self) -> None:
        self.server.remove_client(self)
        super().finish()

    def handle(self) -> None:
        while line := self.rfile.readline():
            self.handle_line(line)

    def handle_line(self, line: bytes) -> None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            self.write_message(
                {"type": "error", "message": f"invalid JSON: {error.msg}"}
            )
            return
        if not isinstance(message, dict):
            self.write_message(
                {"type": "error", "message": "message must be an object"}
            )
            return
        self.write_message(
            handle_message(self.server.config, self.server.controller, message)
        )

    def write_message(self, message: Mapping[str, object]) -> None:
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        with self._write_lock:
            try:
                self.wfile.write(data)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.server.remove_client(self)


def start_control_server(
    config: Twitcho, controller: ControlController
) -> tuple[ControlServer, threading.Thread]:
    server = ControlServer(config, controller)
    thread = threading.Thread(target=server.serve_forever, name="TwitchoControl")
    thread.start()
    return server, thread


def stop_control_server(
    server: ControlServer | None, thread: threading.Thread | None
) -> None:
    if server is None or thread is None:
        return
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def handle_message(
    config: Twitcho,
    controller: ControlController,
    message: Mapping[str, object],
) -> dict[str, object]:
    message_type = message.get("type")
    if message_type == "hello":
        if (
            config.control_token is not None
            and message.get("token") != config.control_token
        ):
            return {"type": "error", "message": "invalid control token"}
        return {"type": "hello", "version": 1, "server": "twitcho"}
    if message_type == "command":
        return controller.handle_command(message)
    return {"type": "error", "message": f"unknown message type {message_type}"}


def typed_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def command_payload(message: Mapping[str, object]) -> dict[str, object]:
    return {k: v for k, v in message.items() if k not in CONTROL_FIELDS}


CONTROL_FIELDS = {"type", "id", "command"}
QUEUED_COMMANDS = {"stop", "update_stream_info", "chat", "announce", "clip", "marker"}
