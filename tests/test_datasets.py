"""Loader checks on the real Kaggle files; skipped when data/raw is not downloaded."""
from pathlib import Path

import pytest

from growth_os.datasets import fbads, olist
from growth_os.hub import store

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
need = pytest.mark.skipif(not (RAW / "olist_marketing_qualified_leads_dataset.csv").is_file(), reason="Kaggle data not downloaded")


@need
def test_olist_loads_every_lead_and_never_counts_missing_value_as_zero(tmp_path):
    out = olist.load(RAW, tmp_path / "o.sqlite")
    assert out["leads"] == 8000 and out["won"] == 842
    with store.connect(tmp_path / "o.sqlite", read_only=True) as db:
        assert db.execute("SELECT SUM(won) FROM v_qualified").fetchone()[0] == 842
        # deals signed too late for a full 90 days of orders stay NULL, never 0
        assert db.execute("SELECT COUNT(*) FROM leads WHERE stage = 'Ganado' AND value_after_90d IS NULL").fetchone()[0] == 842 - out["won_with_full_90d_window"]


@need
def test_fbads_totals_match_the_source(tmp_path):
    out = fbads.load(RAW, tmp_path / "f.sqlite")
    assert out == {"ads": 1143, "spend": 58705.23, "conversions": 3264, "approved": 1079}
