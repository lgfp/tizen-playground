# tizentv

Administer a Samsung Tizen TV from the command line: list and uninstall apps, launch apps,
install `.wgt` packages, reboot, run raw shell commands. Pure Python, no dependencies; it drives
Samsung's `sdb` tool.

## One-time TV setup
1. Install [Tizen Studio](https://developer.tizen.org/development/tizen-studio/download) (or just the `sdb` binary) and put its `tools/` dir on `PATH`.
2. On the TV: Apps -> press `1 2 3 4 5` on the remote -> **Developer mode ON**, set **Host PC IP** to your computer's IP, then reboot the TV.
3. `pip install -e .` (or `python -m tizentv ...`).

## Usage
```
tizentv --host 192.168.1.50 info
tizentv --host 192.168.1.50 apps --filter netflix
tizentv --host 192.168.1.50 apps --raw          # unparsed TV output, if the list looks wrong
tizentv --host 192.168.1.50 uninstall "Disney+" --dry-run
tizentv --host 192.168.1.50 uninstall org.tizen.browser -y
tizentv --host 192.168.1.50 uninstall X --method tizen   # Tizen Studio CLI instead
tizentv --host 192.168.1.50 reboot
```
`uninstall` shows what it will remove, writes a JSON backup of the full app list
(`tv-apps-<timestamp>.json`), and asks before acting (`-y` to skip).

## Network API mode (no Developer Mode)
```
pip install -e '.[ws]'
tizentv --host 192.168.1.50 ws info
tizentv --host 192.168.1.50 ws apps --filter netflix     # first run: choose Allow on the TV
tizentv --host 192.168.1.50 ws launch YouTube
tizentv --host 192.168.1.50 ws key KEY_HOME KEY_MENU     # KEY_0..KEY_9 work too
```
Same API the SmartThings remote uses; the token is cached in `~/.config/tizentv/tokens.json`.
It can list/launch apps and send keys, but **cannot uninstall** (Samsung doesn't expose that).
Samsung has changed this API between firmware generations, so `ws apps` may be empty on some 2024 models.

## Caveats
- Tested only against a fake `sdb` (`pytest`); **not yet run against a real TV**. The `applist` output
  format and the `vd_appuninstall` command vary by model year/firmware, so start with `apps --raw` and `--dry-run`.
- Newer (2023+) firmware restricts sdb shell access on some models; if `uninstall` fails, try `--method tizen`
  (only works for apps you installed yourself).
- Removing system apps can break TV features; the backup lists what was there, but apps can't be re-added from it automatically.
