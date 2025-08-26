import math, os

def get_bb_value():
    try:
        return float(os.getenv("POKERIA_BB", "1.0"))
    except Exception:
        return 1.0

def _clamp(x, lo, hi):
    try:
        x = float(x)
    except Exception:
        return lo
    if math.isnan(x) or math.isinf(x): return lo
    return max(lo, min(hi, x))

def _default_percent(street: int) -> float:
    # 0=preflop, 1=flop, 2=turn, 3=river
    return {0:0.0, 1:0.50, 2:0.60, 3:0.75}.get(int(street), 0.50)

def _percent_to_bb(pot_eur: float, percent: float, bb_eur: float) -> float:
    if bb_eur <= 0: bb_eur = 1.0
    return (float(pot_eur) * float(percent)) / float(bb_eur)

def _bb_to_percent(size_bb: float, pot_eur: float, bb_eur: float) -> float:
    if pot_eur <= 0: return 0.0
    return (float(size_bb) * float(bb_eur)) / float(pot_eur)

def finalize_action(raw: dict, dbg: dict) -> dict:
    """
    Normalise la sortie LLM en:
    {"type","size_bb","percent","confidence","rationale"}
    + defaults sûrs.
    """
    action = str((raw or {}).get("action", "none")).lower().strip()
    if action not in {"fold","call","raise","none"}:
        action = "none"

    size_bb_in = raw.get("size_bb", None)
    percent_in = raw.get("percent", raw.get("%pot", None))
    conf_in    = raw.get("confidence", None)
    reason     = str((raw or {}).get("reason","")).strip()

    pot = float(dbg.get("pot_size", 0.0) or 0.0)
    bb  = get_bb_value()
    street = int(dbg.get("street", 0) or 0)
    to_call = float(dbg.get("to_call", 0.0) or 0.0)

    conf = _clamp(conf_in if conf_in is not None else 0.7, 0.0, 1.0)
    if len(dbg.get("hero_cards", [])) < 2: conf = min(conf, 0.4)
    if street == 0: conf = min(conf, 0.6)

    if action in {"none","fold","call"}:
        size_bb = (to_call / bb) if (action=="call" and bb>0 and to_call>0) else 0.0
        return {"type": action, 
                "size_bb": round(size_bb, 2), 
                "percent": 0.0,
                "confidence": conf, 
                "rationale": reason}

    # action == "raise"
    if size_bb_in is not None:
        size_bb = _clamp(size_bb_in, 0.0, 1000.0)
        percent = _bb_to_percent(size_bb, pot, bb) if pot > 0 else 0.0
    elif percent_in is not None:
        percent = _clamp(percent_in, 0.0, 2.0)  # max 200% pot
        size_bb = _percent_to_bb(pot, percent, bb)
    else:
        percent = _default_percent(street)
        size_bb = _percent_to_bb(pot, percent, bb)

    return {"type": "raise", "size_bb": round(size_bb,2), "percent": round(percent,3),
            "confidence": conf, "rationale": reason}
