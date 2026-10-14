"""Download public layout/font resources; no manuscript is read or transmitted."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paperbridge.layout_runtime import initialize, CACHE

initialize()
from babeldoc.assets.assets import warmup, generate_all_assets_file_list

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print("正在下载并校验本地排版模型、字体和字符映射；不读取论文。", flush=True)
    warmup()
    metadata = generate_all_assets_file_list()
    (CACHE / "ready.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    print("本地排版资源已准备好。", flush=True)
