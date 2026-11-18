"""Samsung Smart TV network API (the one the SmartThings remote uses).

No Developer Mode needed. First connection shows an "Allow" prompt on the TV;
the token it returns is cached so later runs don't ask again.

Can: read device info, list/launch apps, send remote keys.
Cannot: uninstall apps (Samsung doesn't expose that on this API).
"""
from __future__ import annotations

import base64
import json
import ssl
import urllib.request
from pathlib import Path
from typing import Callable

from .sdb import SdbError

TOKEN_FILE = Path.home() / ".config" / "tizentv" / "tokens.json"


def _default_connector(url: str, timeout: float):
    try:
        import websocket  # websocket-client
    except ImportError:
        raise SdbError("websocket-client missing: run `uv sync`") from None
    # TV uses a self-signed cert; this only ever talks to a LAN address you typed.
    return websocket.create_connection(url, timeout=timeout, sslopt={"cert_reqs": ssl.CERT_NONE})


def _default_http_get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode()


class RemoteWs:
    def __init__(self, host: str, port: int = 8002, name: str = "tizentv",
                 token_file: Path = TOKEN_FILE,
                 connector: Callable = _default_connector,
                 http_get: Callable = _default_http_get):
        self.host, self.port, self.name = host, port, name
        self.token_file, self._connector, self._http_get = Path(token_file), connector, http_get
        self._ws = None

    # --- token cache --------------------------------------------------------
    def _token(self) -> str | None:
        try:
            return json.loads(self.token_file.read_text()).get(self.host)
        except (OSError, ValueError):
            return None

    def _save_token(self, token: str) -> None:
        try:
            data = json.loads(self.token_file.read_text())
        except (OSError, ValueError):
            data = {}
        data[self.host] = token
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(data))
        self.token_file.chmod(0o600)

    # --- connection ---------------------------------------------------------
    def open(self, timeout: float = 30) -> None:
        name = base64.b64encode(self.name.encode()).decode()
        url = f"wss://{self.host}:{self.port}/api/v2/channels/samsung.remote.control?name={name}"
        if t := self._token():
            url += f"&token={t}"
        try:
            self._ws = self._connector(url, timeout)
            msg = json.loads(self._ws.recv())
        except SdbError:
            raise
        except Exception as e:
            raise SdbError(f"Could not reach {self.host}:{self.port} ({e}). TV on and on the same network?") from e
        event = msg.get("event")
        if event != "ms.channel.connect":
            raise SdbError(
                f"TV refused the connection ({event}). On the TV: Settings > General > "
                "External Device Manager > Device Connect Manager > Access Notification "
                "must be on, and choose Allow when prompted. If you pressed Deny earlier, "
                "clear the entry under Device List."
            )
        if tok := (msg.get("data") or {}).get("token"):
            self._save_token(str(tok))

    def close(self) -> None:
        if self._ws:
            self._ws.close()
            self._ws = None

    def _send(self, payload: dict) -> None:
        self._ws.send(json.dumps(payload))

    def _wait_for(self, event: str, limit: int = 20) -> dict:
        for _ in range(limit):
            msg = json.loads(self._ws.recv())
            if msg.get("event") == event:
                return msg
        raise SdbError(f"TV never answered {event!r} (this firmware may not support it).")

    # --- operations ---------------------------------------------------------
    def info(self) -> dict:
        return json.loads(self._http_get(f"http://{self.host}:8001/api/v2/"))

    def key(self, key: str) -> None:
        self._send({"method": "ms.remote.control", "params": {
            "Cmd": "Click", "DataOfCmd": key, "Option": "false", "TypeOfRemote": "SendRemoteKey"}})

    def apps(self) -> list[dict]:
        self._send({"method": "ms.channel.emit", "params": {"event": "ed.installedApp.get", "to": "host"}})
        msg = self._wait_for("ed.installedApp.get")
        data = msg.get("data")
        if isinstance(data, dict):
            data = data.get("data")
        return list(data or [])

    def launch(self, app_id: str) -> None:
        self._send({"method": "ms.channel.emit", "params": {
            "event": "ed.apps.launch", "to": "host",
            "data": {"appId": app_id, "action_type": "DEEP_LINK"}}})
