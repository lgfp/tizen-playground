import json
from tizentv.cli import main
from tizentv.wsapi import RemoteWs


class FakeWs:
    def __init__(self, replies):
        self.sent, self.replies, self.closed = [], list(replies), False
    def send(self, s): self.sent.append(json.loads(s))
    def recv(self): return json.dumps(self.replies.pop(0))
    def close(self): self.closed = True


CONNECT = {"event": "ms.channel.connect", "data": {"token": "12345678"}}
APPS = {"event": "ed.installedApp.get", "data": {"data": [
    {"appId": "3201907018807", "name": "Netflix"}, {"appId": "111299001912", "name": "YouTube"}]}}


def run(argv, tmp_path, replies):
    fake = FakeWs(replies)
    urls = []
    def conn(url, timeout):
        urls.append(url); return fake
    def factory(host, port):
        return RemoteWs(host, port, token_file=tmp_path / "t.json", connector=conn,
                        http_get=lambda u: json.dumps({"device": {"modelName": "24_PONTUSM_FTV"}}))
    rc = main(["--host", "1.2.3.4", *argv], ws_factory=factory)
    return rc, fake, urls


def test_token_saved_and_reused(tmp_path):
    rc, fake, urls = run(["ws", "key", "KEY_HOME"], tmp_path, [CONNECT])
    assert rc == 0 and fake.closed
    assert fake.sent[0]["params"]["DataOfCmd"] == "KEY_HOME"
    assert json.loads((tmp_path / "t.json").read_text()) == {"1.2.3.4": "12345678"}
    _, _, urls2 = run(["ws", "key", "KEY_MENU"], tmp_path, [CONNECT])
    assert "token=12345678" in urls2[0] and "token" not in urls[0]


def test_launch_by_name(tmp_path):
    rc, fake, _ = run(["ws", "launch", "netflix"], tmp_path, [CONNECT, APPS])
    assert rc == 0
    assert fake.sent[-1]["params"]["data"]["appId"] == "3201907018807"


def test_denied(tmp_path, capsys):
    rc, _, _ = run(["ws", "apps"], tmp_path, [{"event": "ms.channel.unauthorized"}])
    assert rc == 1 and "Allow" in capsys.readouterr().err


def test_info_needs_no_websocket(tmp_path, capsys):
    rc, fake, urls = run(["ws", "info"], tmp_path, [])
    assert rc == 0 and not urls and "24_PONTUSM_FTV" in capsys.readouterr().out
