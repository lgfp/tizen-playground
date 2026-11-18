# tizentv

Administer a Samsung Tizen TV from the command line: list and uninstall apps, launch apps,
install `.wgt` packages, reboot, run raw shell commands. Pure Python, managed with uv; it drives
Samsung's `sdb` tool, or the TV's network API.

## One-time TV setup
1. Install [Tizen Studio](https://developer.tizen.org/development/tizen-studio/download) (or just the `sdb` binary) and put its `tools/` dir on `PATH`.
2. On the TV: Apps -> press `1 2 3 4 5` on the remote -> **Developer mode ON**, set **Host PC IP** to your computer's IP, then reboot the TV.
3. Install [uv](https://docs.astral.sh/uv/) (`brew install uv`), then `uv sync` in this folder.

## Usage
```
uv run tizentv --host 192.168.1.50 info
uv run tizentv --host 192.168.1.50 apps --filter netflix
uv run tizentv --host 192.168.1.50 apps --raw          # unparsed TV output, if the list looks wrong
uv run tizentv --host 192.168.1.50 uninstall "Disney+" --dry-run
uv run tizentv --host 192.168.1.50 uninstall RN1MCdNq8t.Netflix -y          # by app id
uv run tizentv --host 192.168.1.50 uninstall --file remove.txt --dry-run   # bulk: one id/name per line
uv run tizentv --host 192.168.1.50 uninstall X --method tizen   # Tizen Studio CLI instead
uv run tizentv --host 192.168.1.50 reboot
```
`uninstall` shows what it will remove, writes a JSON backup of the full app list
(`tv-apps-<timestamp>.json`), and asks before acting (`-y` to skip). It uses `sdb uninstall`
(retry with the package id if the app id doesn't take), then re-reads the app list and reports
what is really gone: the TV says `val[ok]` even when nothing happened. System packages
(`org.tizen.*`, `com.samsung.*` and a few store helpers the TV needs) are skipped unless `--force`.
Pre-installed apps come back after a Smart Hub reset or factory reset.

## Network API mode (no Developer Mode)
```
uv run tizentv --host 192.168.1.50 ws info
uv run tizentv --host 192.168.1.50 ws apps --filter netflix     # first run: choose Allow on the TV
uv run tizentv --host 192.168.1.50 ws launch YouTube
uv run tizentv --host 192.168.1.50 ws key KEY_HOME KEY_MENU     # KEY_0..KEY_9 work too
```
Same API the SmartThings remote uses; the token is cached in `~/.config/tizentv/tokens.json`.
It can list/launch apps and send keys, but **cannot uninstall** (Samsung doesn't expose that).
Samsung has changed this API between firmware generations, so `ws apps` may be empty on some 2024 models.

## Caveats
- Tested only against a fake `sdb` (`pytest`); **not yet run against a real TV**. The `applist` output
  format and the `vd_appuninstall` command vary by model year/firmware, so start with `apps --raw` and `--dry-run`.
- Port 26101 refused although `curl http://<tv>:8001/api/v2/` shows `developerMode: "1"` means `sdbd`
  didn't start. The flag is read at boot: unplug the TV (One Connect box) from the wall for 60 s,
  without reopening the Developer Mode dialog afterwards. If still closed: toggle Developer Mode off,
  cold boot, on with the IP, cold boot.
- `--method vd` (`vd_appuninstall` via sdb shell) is for older firmware; retail firmware disables
  sdb shell for most commands.
- Removing system apps can break TV features; the backup lists what was there, but apps can't be re-added from it automatically.

## Tests
```
uv run pytest
```
