import json
import pytest
from tizentv.cli import main
from tizentv.sdb import Result, Tv, parse_applist, SdbError

APPLIST = """
	Application List for user 5001
	Name                 AppID
	-------------------  ------------------
	'Netflix'  'org.tizen.netflix-app'
	'Disney+'  'MCmYXNxgcu.DisneyPlus'
	'Web Browser'  'org.tizen.browser'
"""


class FakeTv:
    """Stands in for sdb: records calls, answers like a TV."""
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        a = " ".join(argv)
        if "connect" in a:
            return Result(0, "connected to 1.2.3.4:26101")
        if a.endswith("0 vd_applist") or a.endswith("0 applist"):
            return Result(0, APPLIST)
        if "vd_appuninstall" in a:
            return Result(0, "uninstall ok")
        return Result(0, "")


def run(argv, fake, confirm=lambda _: "y"):
    return main(["--host", "1.2.3.4", *argv],
                tv_factory=lambda h, p: Tv(h, p, runner=fake), confirm=confirm)


def test_parse():
    apps = parse_applist(APPLIST)
    assert [a.app_id for a in apps] == ["org.tizen.netflix-app", "MCmYXNxgcu.DisneyPlus", "org.tizen.browser"]


def test_uninstall_by_name_and_backup(tmp_path):
    fake = FakeTv()
    assert run(["uninstall", "netflix", "--backup-dir", str(tmp_path)], fake) == 0
    assert any(c[-2:] == ["vd_appuninstall", "org.tizen.netflix-app"] for c in fake.calls)
    backup = next(tmp_path.glob("tv-apps-*.json"))
    assert len(json.loads(backup.read_text())) == 3


def test_decline_does_nothing(tmp_path):
    fake = FakeTv()
    assert run(["uninstall", "netflix", "--backup-dir", str(tmp_path)], fake, confirm=lambda _: "n") == 1
    assert not any("vd_appuninstall" in " ".join(c) for c in fake.calls)


def test_dry_run_and_unknown(tmp_path, capsys):
    fake = FakeTv()
    assert run(["uninstall", "org.tizen.browser", "--dry-run"], fake) == 0
    assert not any("vd_appuninstall" in " ".join(c) for c in fake.calls)
    assert run(["uninstall", "nope", "--backup-dir", str(tmp_path)], fake) == 1


def test_connect_failure_message():
    def bad(argv):
        return Result(0, "failed to connect to 1.2.3.4:26101")
    with pytest.raises(SdbError, match="Developer Mode"):
        Tv("1.2.3.4", runner=bad).connect()


def test_uninstall_from_file(tmp_path):
    f = tmp_path / "remove.txt"
    f.write_text("# junk apps\nNetflix\norg.tizen.browser  # browser\n\n")
    fake = FakeTv()
    assert run(["uninstall", "--file", str(f), "-y", "--backup-dir", str(tmp_path)], fake) == 0
    removed = [c[-1] for c in fake.calls if "vd_appuninstall" in c]
    assert removed == ["org.tizen.netflix-app", "org.tizen.browser"]
