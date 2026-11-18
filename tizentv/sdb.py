"""Thin wrapper around Samsung's `sdb` (Smart Development Bridge).

All TV access goes through one `Runner` callable so tests can fake the TV.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

DEFAULT_PORT = 26101


class SdbError(RuntimeError):
    pass


@dataclass
class Result:
    code: int
    out: str


Runner = Callable[[Sequence[str]], Result]


def subprocess_runner(argv: Sequence[str]) -> Result:
    if shutil.which(argv[0]) is None:
        raise SdbError(
            f"`{argv[0]}` not found on PATH. Install Tizen Studio (or the standalone "
            "sdb tool) and add its `tools/` directory to PATH."
        )
    p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    return Result(p.returncode, (p.stdout + p.stderr).strip())


class Tv:
    def __init__(self, host: str, port: int = DEFAULT_PORT, runner: Runner = subprocess_runner):
        self.host, self.port, self._run = host, port, runner

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"

    def sdb(self, *args: str) -> Result:
        return self._run(["sdb", *args])

    def connect(self) -> str:
        r = self.sdb("connect", self.target)
        if r.code != 0 or "failed" in r.out.lower() or "cannot" in r.out.lower():
            raise SdbError(
                f"Could not connect to {self.target}: {r.out}\n"
                "Check: TV Developer Mode is ON and the TV's 'Host PC IP' is this "
                "computer's IP (Apps panel -> type 12345 -> Developer mode), then "
                "reboot the TV."
            )
        return r.out

    def shell(self, *cmd: str) -> Result:
        return self.sdb("-s", self.target, "shell", *cmd)

    def capability(self) -> dict[str, str]:
        r = self.sdb("-s", self.target, "capability")
        info = {}
        for line in r.out.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                info[k.strip()] = v.strip()
        return info

    # --- apps -------------------------------------------------------------

    def list_apps(self) -> tuple[list["App"], str]:
        """Returns (apps, raw_output). Output format varies by firmware, so the
        raw text is returned too (see `apps --raw`)."""
        r = self.shell("0", "applist")
        if r.code != 0:
            raise SdbError(f"applist failed: {r.out}")
        return parse_applist(r.out), r.out

    def uninstall(self, app_id: str, method: str = "vd") -> Result:
        if method == "tizen":
            return self._run(["tizen", "uninstall", "-p", app_id, "-t", self.target])
        return self.shell("0", "vd_appuninstall", app_id)

    def install(self, wgt_path: str) -> Result:
        return self._run(["tizen", "install", "-n", wgt_path, "-t", self.target])

    def launch(self, app_id: str) -> Result:
        return self.shell("0", "was_execute", app_id)

    def reboot(self) -> Result:
        return self.shell("reboot")


@dataclass(frozen=True)
class App:
    name: str
    app_id: str


def parse_applist(text: str) -> list[App]:
    """Parse `sdb shell 0 applist`.

    Known shape: rows like `'Netflix'  'org.tizen.netflix-app'` (name then id),
    under a header. Tolerates tab/space padding and unquoted ids. Lines that
    don't look like a row are ignored; check `apps --raw` if a TV differs.
    """
    apps: list[App] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or set(line) <= {"-", " ", "\t"}:
            continue
        quoted = _quoted(line)
        if len(quoted) >= 2:
            apps.append(App(quoted[0], quoted[1]))
        elif len(quoted) == 1 and _looks_like_id(quoted[0]):
            apps.append(App(quoted[0], quoted[0]))
    return apps


def _quoted(line: str) -> list[str]:
    out, cur, q = [], [], None
    for ch in line:
        if q:
            if ch == q:
                out.append("".join(cur))
                cur, q = [], None
            else:
                cur.append(ch)
        elif ch in "'\"":
            q = ch
    return out


def _looks_like_id(s: str) -> bool:
    return "." in s and " " not in s
