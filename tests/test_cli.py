import json
import pytest
from tizentv.cli import main
from tizentv.sdb import Result, Tv, parse_applist, SdbError, is_protected

APPS = [("Netflix", "RN1MCdNq8t.Netflix"), ("Disney+", "MCmYXNxgcu.DisneyPlus"),
        ("Web Browser", "org.tizen.browser"), ("Stubborn", "AbCdEfGhIj.Stubborn")]


def applist(apps):
    rows = "\n".join(f"\t'{n}'  '{i}'" for n, i in apps)
    return f"\n\tApplication List for user 5001\n\tName  AppID\n\t----  -----\n{rows}\n"


class FakeTv:
    """Stands in for sdb: records calls, answers like a TV, actually removes apps."""
    def __init__(self, needs_pkgid=()):
        self.calls, self.apps, self.needs_pkgid = [], list(APPS), set(needs_pkgid)

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        a = " ".join(argv)
        if "connect" in a:
            return Result(0, "connected to 1.2.3.4:26101")
        if a.endswith("0 vd_applist") or a.endswith("0 applist"):
            return Result(0, applist(self.apps))
        if "uninstall" in argv:
            target = argv[-1]
            for n, i in list(self.apps):
                if i == target and i not in self.needs_pkgid or i.split(".")[0] == target:
                    self.apps.remove((n, i))
            return Result(0, "val[ok]")  # TVs say ok even when nothing happened
        return Result(0, "")


def run(argv, fake, confirm=lambda _: "y"):
    return main(["--host", "1.2.3.4", *argv],
                tv_factory=lambda h, p: Tv(h, p, runner=fake), confirm=confirm)


def uninstalls(fake):
    return [c[-1] for c in fake.calls if "uninstall" in c]


def test_parse():
    assert [a.app_id for a in parse_applist(applist(APPS))] == [i for _, i in APPS]


def test_uninstall_by_name_and_backup(tmp_path):
    fake = FakeTv()
    assert run(["uninstall", "netflix", "--backup-dir", str(tmp_path)], fake) == 0
    assert uninstalls(fake) == ["RN1MCdNq8t.Netflix"]
    assert ["sdb", "-s", "1.2.3.4:26101", "uninstall", "RN1MCdNq8t.Netflix"] in fake.calls
    assert len(json.loads(next(tmp_path.glob("tv-apps-*.json")).read_text())) == 4


def test_ok_is_not_trusted_and_pkgid_fallback(tmp_path, capsys):
    fake = FakeTv(needs_pkgid={"AbCdEfGhIj.Stubborn"})
    assert run(["uninstall", "Stubborn", "--backup-dir", str(tmp_path), "-y"], fake) == 0
    assert uninstalls(fake) == ["AbCdEfGhIj.Stubborn", "AbCdEfGhIj"]
    assert ("Stubborn", "AbCdEfGhIj.Stubborn") not in fake.apps


def test_still_there_reported(tmp_path, capsys):
    class Never(FakeTv):
        def __call__(self, argv):
            if "uninstall" in argv:
                self.calls.append(list(argv)); return Result(0, "val[ok]")
            return super().__call__(argv)
    fake = Never()
    assert run(["uninstall", "Disney+", "-y", "--backup-dir", str(tmp_path)], fake) == 1
    assert "STILL THERE MCmYXNxgcu.DisneyPlus" in capsys.readouterr().out


def test_protected_skipped(tmp_path, capsys):
    fake = FakeTv()
    assert run(["uninstall", "Web Browser", "-y", "--backup-dir", str(tmp_path)], fake) == 1
    assert uninstalls(fake) == [] and "protected" in capsys.readouterr().err
    assert is_protected("com.samsung.tv.store") and not is_protected("RN1MCdNq8t.Netflix")


def test_decline_does_nothing(tmp_path):
    fake = FakeTv()
    assert run(["uninstall", "netflix", "--backup-dir", str(tmp_path)], fake, confirm=lambda _: "n") == 1
    assert uninstalls(fake) == []


def test_dry_run_and_unknown(tmp_path):
    fake = FakeTv()
    assert run(["uninstall", "Disney+", "--dry-run"], fake) == 0
    assert uninstalls(fake) == []
    assert run(["uninstall", "nope", "--backup-dir", str(tmp_path)], fake) == 1


def test_uninstall_from_file(tmp_path):
    f = tmp_path / "remove.txt"
    f.write_text("# junk apps\nNetflix\nMCmYXNxgcu.DisneyPlus  # disney\n\n")
    fake = FakeTv()
    assert run(["uninstall", "--file", str(f), "-y", "--backup-dir", str(tmp_path)], fake) == 0
    assert uninstalls(fake) == ["RN1MCdNq8t.Netflix", "MCmYXNxgcu.DisneyPlus"]


def test_connect_failure_message():
    with pytest.raises(SdbError, match="Developer Mode"):
        Tv("1.2.3.4", runner=lambda argv: Result(0, "failed to connect to 1.2.3.4:26101")).connect()
