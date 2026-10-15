"""Separate installed application files from writable personal data."""
import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("PAPERBRIDGE_HOME", CODE_ROOT)).resolve()
WINDOWS = os.name == "nt"


def hidden_process():
    return {"creationflags": 0x08000000} if WINDOWS else {}
