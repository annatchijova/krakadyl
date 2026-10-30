"""The live closing script must keep working offline, and must refuse a
live run before any call when a guard rail is missing."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from demo import run_level3_live_closing as closing  # noqa: E402


def _run(monkeypatch, tmp_path, *argv):
    monkeypatch.setattr(closing, "OUT_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_level3_live_closing.py", *argv])
    return closing.main()


def test_rehearsal_runs_both_closing_scenarios_without_promotion(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, "--dry-run", "--scripted-outcome", "no_discriminating_change") == 0
    report = json.loads(next(tmp_path.glob("*/report.json")).read_text())
    assert report["mode"] == "dry-run" and report["sent_to_meta"] == "nothing"
    a, b = report["runs"]
    assert a["sidecar_status"] == "empty" and b["sidecar_status"] == "parsed"
    assert not a["promoted_without_evaluation"] and not b["promoted_without_evaluation"]
    assert a["requirement_after"]["resolved"] is False and b["requirement_after"]["resolved"] is False
    assert b["evaluation"]["evaluator_identity"] == "investigator-C"


@pytest.mark.parametrize("argv, env_key", [
    (["--live", "--max-usd-micros", "5000", "--meta-retention-reviewed"], None),
    (["--live", "--max-usd-micros", "4999", "--meta-retention-reviewed"], "k"),
    (["--live", "--max-usd-micros", "5000"], "k"),
    (["--live", "--max-usd-micros", "5000", "--meta-retention-reviewed", "--scripted-outcome", "supports_requirement"], "k"),
])
def test_live_guard_rails_refuse_before_anything_happens(monkeypatch, tmp_path, argv, env_key):
    if env_key:
        monkeypatch.setenv("META_API_KEY", env_key)
    else:
        monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        _run(monkeypatch, tmp_path, *argv)
    assert list(tmp_path.iterdir()) == []
