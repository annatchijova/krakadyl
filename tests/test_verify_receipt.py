import json
import subprocess
import sys


def test_empty_receipt_chain_is_not_reported_as_verified(tmp_path):
    chain = tmp_path / "empty-chain.json"
    chain.write_text(json.dumps([]), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "tools/verify_receipt.py", str(chain)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "BROKEN" in result.stdout


def test_malformed_receipt_entry_is_reported_without_a_traceback(tmp_path):
    chain = tmp_path / "malformed-chain.json"
    chain.write_text(json.dumps([{}]), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "tools/verify_receipt.py", str(chain)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "BROKEN at entry 0" in result.stdout
    assert "Traceback" not in result.stderr
