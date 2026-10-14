"""Keep all third-party layout resources inside the project workspace."""
import os
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "babeldoc"


def initialize():
    import onnxruntime
    # Layout inference does not need background platform statistics. Disable
    # them before creating sessions, including resource-install/test sessions.
    onnxruntime.disable_telemetry_events()
    # BabelDOC 0.6.4 has a hard-coded Path.home() cache. Scope the override to
    # importing its constants; do not change HOME or other process environment.
    with patch.object(Path, "home", return_value=ROOT / ".cache" / "layout-home"):
        import babeldoc.const as const
    const.CACHE_FOLDER = CACHE
    const.TIKTOKEN_CACHE_FOLDER = CACHE / "tiktoken"
    const.TIKTOKEN_CACHE_FOLDER.mkdir(parents=True, exist_ok=True)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(const.TIKTOKEN_CACHE_FOLDER)


def ready():
    return (CACHE / "ready.json").is_file()
