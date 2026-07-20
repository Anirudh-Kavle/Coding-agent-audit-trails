"""Download the local session-summarizer model into ~/.flight-recorder/models/.

One-time, ~1.0 GB. The viewer's "Generate session summary" button appears
automatically once a .gguf file exists there (and llama-cpp-python is
installed). Everything runs on-device; nothing is sent to any cloud service.

Usage: python scripts/get_model.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf"
DEST = Path.home() / ".flight-recorder" / "models" / "Qwen3-1.7B-Q4_K_M.gguf"


def _progress(blocks: int, block_size: int, total: int) -> None:
    done = blocks * block_size
    if total > 0:
        print(f"\r  {min(100, done * 100 // total)}%  ({done // (1 << 20)} MB)", end="", flush=True)


def main() -> int:
    if DEST.exists():
        print(f"Model already present: {DEST}")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_name(DEST.name + ".part")
    print(f"Downloading Qwen3-1.7B Q4_K_M (~1.0 GB)\n  from {URL}\n  to   {DEST}")
    try:
        urllib.request.urlretrieve(URL, tmp, reporthook=_progress)
    except KeyboardInterrupt:
        print("\nCancelled; partial file removed.")
        tmp.unlink(missing_ok=True)
        return 1
    tmp.rename(DEST)
    print(f"\nDone. Open the viewer and use the summary button, or rerun `fr ui`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
