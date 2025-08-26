import csv, json
from pathlib import Path
from datetime import datetime

LOG_DIR = Path("logs"); LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR/"decisions.csv"

FIELDS = ["ts","model","street","position","spr","pot","stack",
          "hero_cards","board_cards","action","size_bb","percent","confidence","reason","raw"]

def append_decision(model: str, dbg: dict, decision: dict, raw: dict):
    is_new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new: w.writeheader()
        w.writerow({
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "model": model,
            "street": dbg.get("street"),
            "position": dbg.get("position"),
            "spr": round(float(dbg.get("spr", 0.0)), 2),
            "pot": dbg.get("pot_size", 0.0),
            "stack": dbg.get("hero_stack", 0.0),
            "hero_cards": " ".join(dbg.get("hero_cards", [])),
            "board_cards": " ".join(dbg.get("board_cards", [])),
            "action": decision.get("type"),
            "size_bb": decision.get("size_bb"),
            "percent": decision.get("percent"),
            "confidence": decision.get("confidence"),
            "reason": decision.get("rationale"),
            "raw": json.dumps(raw, ensure_ascii=False),
        })
