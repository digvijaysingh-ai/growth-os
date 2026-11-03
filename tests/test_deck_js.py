"""Runs the deck's JavaScript tests (tests/deck.test.mjs) so `pytest` covers them. Without Node 20+ the test skips,
unless CI or REQUIRE_NODE is set, where a missing Node fails instead."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_deck_state_in_node():
    node = shutil.which("node")
    required = bool(os.environ.get("CI") or os.environ.get("REQUIRE_NODE"))
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip() if node else ""
    major = int(m.group(1)) if (m := re.match(r"v(\d+)", version)) else 0
    if major < 20:
        msg = f"Node 20+ not found ({version or 'no node on PATH'}); set REQUIRE_NODE=1 to fail instead"
        if required:
            pytest.fail(msg)
        pytest.skip(msg)
    r = subprocess.run([node, "--test", str(ROOT / "tests" / "deck.test.mjs")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
