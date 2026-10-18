#!/usr/bin/env python3
"""Print the real test total (never swallow it with -qq)."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q"],
    capture_output=True, text=True, cwd=root,
)
print(out.stdout.strip().splitlines()[-1])
sys.exit(out.returncode)
