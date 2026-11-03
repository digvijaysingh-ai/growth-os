"""The publish scan (GOS-106) catches keys, local paths and persona names in what will be published, never prints a
secret in full, honours reviewed allowlist entries, and refuses a build stamped stale."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publish_scan", ROOT / "scripts" / "publish_scan.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)

FAKE_KEY = "sk-ant-" + "abcdefghijklmnop1234"


def test_key_is_caught_and_masked(tmp_path, capsys):
    (tmp_path / "page.html").write_text(f"<p>token {FAKE_KEY}</p>\n<p>see /Users/someone/state</p>")
    assert scan.main(["--deployed", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "page.html:1:key" in err and "page.html:2:local-path" in err and "GOS-106" in err
    assert FAKE_KEY not in err


def test_persona_names_count_only_on_deployed_pages(tmp_path):
    (tmp_path / "index.html").write_text("approved by Dana (leadership)")
    assert any(":persona" in h for h in scan.scan([tmp_path]))


def test_allowlist_and_stale_stamp(tmp_path, monkeypatch, capsys):
    (tmp_path / "notes.md").write_text("example path /Users/example/project")
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    (tmp_path / "publish-scan.allow").write_text(f"local-path {tmp_path / 'notes.md'} documented example\n")
    assert scan.scan([tmp_path]) == []
    (tmp_path / "index.html").write_text('<script type="application/json">{"stale": true}</script>')
    assert scan.main(["--deployed", str(tmp_path)]) == 1
    assert "stale-build" in capsys.readouterr().err
