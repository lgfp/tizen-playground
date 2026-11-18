"""tizentv - administer a Samsung Tizen TV over sdb."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .sdb import SdbError, Tv, DEFAULT_PORT
from .wsapi import RemoteWs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tizentv", description=__doc__)
    p.add_argument("--host", required=True, help="TV IP address")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="show TV capabilities (model, platform version)")
    a = sub.add_parser("apps", help="list installed apps")
    a.add_argument("--filter", help="case-insensitive substring of name or id")
    a.add_argument("--raw", action="store_true", help="print the TV's unparsed output")
    a.add_argument("--json", action="store_true")

    u = sub.add_parser("uninstall", help="uninstall one or more apps by id or name")
    u.add_argument("apps", nargs="*", help="app ids, or exact names")
    u.add_argument("--file", "-f", help="text file with one app id or name per line (# comments ok)")
    u.add_argument("--yes", "-y", action="store_true", help="don't ask for confirmation")
    u.add_argument("--dry-run", action="store_true")
    u.add_argument("--method", choices=["vd", "tizen"], default="vd",
                   help="vd: `vd_appuninstall` over sdb shell (default); "
                        "tizen: Tizen Studio CLI (only dev-installed apps)")
    u.add_argument("--backup-dir", default=".", help="where the app-list backup is written")

    l = sub.add_parser("launch", help="launch an app")
    l.add_argument("app")
    i = sub.add_parser("install", help="install a .wgt (needs the `tizen` CLI)")
    i.add_argument("wgt")
    sub.add_parser("reboot", help="reboot the TV")
    sh = sub.add_parser("shell", help="run a raw command in the TV's shell")
    sh.add_argument("command", nargs="+")

    ws = sub.add_parser("ws", help="network API (no Developer Mode): info, apps, launch, key")
    ws.add_argument("--ws-port", type=int, default=8002)
    wsub = ws.add_subparsers(dest="ws_cmd", required=True)
    wsub.add_parser("info", help="device info (model, power state, Frame support)")
    wa = wsub.add_parser("apps", help="list installed apps")
    wa.add_argument("--filter")
    wa.add_argument("--json", action="store_true")
    wl = wsub.add_parser("launch", help="launch an app by id or exact name")
    wl.add_argument("app")
    wk = wsub.add_parser("key", help="send remote keys, e.g. KEY_HOME KEY_MENU KEY_1 KEY_2")
    wk.add_argument("keys", nargs="+")
    return p


def resolve(tv_apps, wanted: list[str]):
    """Map user input (id or exact name) to app ids; error on unknown/ambiguous."""
    by_id = {a.app_id: a for a in tv_apps}
    out = []
    for w in wanted:
        if w in by_id:
            out.append(by_id[w])
            continue
        named = [a for a in tv_apps if a.name.lower() == w.lower()]
        if len(named) == 1:
            out.append(named[0])
        elif not named:
            raise SdbError(f"No installed app with id or name {w!r}. Try `apps --filter`.")
        else:
            ids = ", ".join(a.app_id for a in named)
            raise SdbError(f"{w!r} is ambiguous ({ids}); use the app id.")
    return out


def main(argv=None, tv_factory=Tv, confirm=input, ws_factory=RemoteWs) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "ws":
        try:
            return ws_dispatch(ws_factory(args.host, args.ws_port), args)
        except SdbError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    tv = tv_factory(args.host, args.port)
    try:
        tv.connect()
        return dispatch(tv, args, confirm)
    except SdbError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def ws_dispatch(ws, args) -> int:
    if args.ws_cmd == "info":
        d = ws.info()
        dev = d.get("device", {})
        print(f"{dev.get('modelName', '?')}  {dev.get('name', '')}  power={dev.get('PowerState', '?')}"
              f"  frame={dev.get('FrameTVSupport', '?')}  os={dev.get('OS', '?')}")
        return 0
    ws.open()
    try:
        if args.ws_cmd == "key":
            import time
            for k in args.keys:
                ws.key(k)
                time.sleep(0.3)
        elif args.ws_cmd == "apps":
            apps = ws.apps()
            if args.filter:
                f = args.filter.lower()
                apps = [a for a in apps if f in str(a.get("name", "")).lower() or f in str(a.get("appId", "")).lower()]
            if args.json:
                print(json.dumps(apps, indent=2))
            else:
                for a in sorted(apps, key=lambda a: str(a.get("name", "")).lower()):
                    print(f"{a.get('appId', ''):<30} {a.get('name', '')}")
                print(f"{len(apps)} apps", file=sys.stderr)
        elif args.ws_cmd == "launch":
            wanted = args.app
            for a in ws.apps():
                if wanted in (a.get("appId"), a.get("name")) or str(a.get("name", "")).lower() == wanted.lower():
                    wanted = a["appId"]
                    break
            ws.launch(wanted)
            print(f"launch sent: {wanted}")
    finally:
        ws.close()
    return 0


def dispatch(tv, args, confirm) -> int:
    if args.cmd == "info":
        for k, v in sorted(tv.capability().items()):
            print(f"{k}: {v}")
    elif args.cmd == "apps":
        apps, raw = tv.list_apps()
        if args.raw:
            print(raw)
            return 0
        if args.filter:
            f = args.filter.lower()
            apps = [a for a in apps if f in a.name.lower() or f in a.app_id.lower()]
        if args.json:
            print(json.dumps([a.__dict__ for a in apps], indent=2))
        else:
            for a in sorted(apps, key=lambda a: a.name.lower()):
                print(f"{a.app_id:<45} {a.name}")
            print(f"{len(apps)} apps", file=sys.stderr)
    elif args.cmd == "uninstall":
        wanted = list(args.apps)
        if args.file:
            for line in Path(args.file).read_text().splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    wanted.append(line)
        if not wanted:
            raise SdbError("Nothing to uninstall: give app ids/names or --file.")
        apps, raw = tv.list_apps()
        targets = resolve(apps, wanted)
        print("Will uninstall:")
        for a in targets:
            print(f"  {a.app_id}  ({a.name})")
        if args.dry_run:
            return 0
        backup = Path(args.backup_dir) / f"tv-apps-{datetime.now():%Y%m%d-%H%M%S}.json"
        backup.write_text(json.dumps([a.__dict__ for a in apps], indent=2))
        print(f"Backed up full app list to {backup}")
        if not args.yes and confirm("Proceed? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return 1
        failed = 0
        for a in targets:
            r = tv.uninstall(a.app_id, args.method)
            print(f"{'ok  ' if r.code == 0 else 'FAIL'} {a.app_id}: {r.out}")
            failed += r.code != 0
        return 1 if failed else 0
    elif args.cmd == "launch":
        apps, _ = tv.list_apps()
        r = tv.launch(resolve(apps, [args.app])[0].app_id)
        print(r.out)
        return r.code
    elif args.cmd == "install":
        r = tv.install(args.wgt)
        print(r.out)
        return r.code
    elif args.cmd == "reboot":
        print(tv.reboot().out)
    elif args.cmd == "shell":
        r = tv.shell(*args.command)
        print(r.out)
        return r.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
