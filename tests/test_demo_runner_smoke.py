"""Smoke test: verifica che il demo runner sia ancora allineato alla GUI reale.

Se questo test fallisce, tools/demo/demo_runner.py e' fuori sync col codice
del tool: la prossima esecuzione produrra' una demo rotta. Sistema il runner
(aggiornando anche la 'Sezione contratto' nel suo docstring) prima di rilasciare.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "tools" / "demo" / "demo_runner.py"


@pytest.mark.skipif(not RUNNER.exists(), reason="demo runner non presente")
def test_demo_runner_dry_run_ok():
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--dry-run"],
        capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"dry-run fallito.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
