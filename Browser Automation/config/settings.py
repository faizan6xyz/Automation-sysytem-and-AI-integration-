# config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN  = os.getenv("HF_TOKEN", "")
MAX_STEPS = int(os.getenv("MAX_STEPS", 15))
HEADLESS  = os.getenv("HEADLESS", "False").lower() == "true"
def _find_model() -> str:
    # Possible locations to search
    candidates = [
        # From .env override
        os.getenv("HF_MODEL", ""),
        # Common Windows paths
        r"C:/Users/faiza/.cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct/snapshots",
        # Also try via env HOME
        str(Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct/snapshots"),
    ]
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw)
        # Case 1: path IS the snapshots/ folder → grab hash inside
        if p.exists() and p.is_dir() and p.name == "snapshots":
            hashes = sorted([d for d in p.iterdir() if d.is_dir()])
            if hashes:
                resolved = str(hashes[-1])
                print(f"[settings] HF_MODEL resolved to: {resolved}")
                return resolved
        # Case 2: path IS already the hash folder (has config.json inside)
        if p.exists() and (p / "config.json").exists():
            print(f"[settings] HF_MODEL resolved to: {p}")
            return str(p)
        # Case 3: path is models--Qwen--... folder (one level above snapshots)
        snapshots_dir = p / "snapshots"
        if snapshots_dir.exists():
            hashes = sorted([d for d in snapshots_dir.iterdir() if d.is_dir()])
            if hashes:
                resolved = str(hashes[-1])
                print(f"[settings] HF_MODEL resolved to: {resolved}")
                return resolved
    # Fallback: use HF model id (will download if not cached)
    print("[settings] WARNING: local model not found, falling back to HF download: Qwen/Qwen2.5-3B-Instruct")
    return "Qwen/Qwen2.5-3B-Instruct"
HF_MODEL = _find_model()
