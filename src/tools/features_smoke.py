from src.state.builder import build_state
from src.featurize.features import featurize

if __name__ == "__main__":
    st = build_state()
    x, names, dbg = featurize(st)
    print("=== FEATURES ===")
    print("street:", dbg["street"], "position:", dbg["position"], "spr:", round(dbg["spr"],2))
    print("hero:", {k:dbg[k] for k in ["is_pair","is_suited","is_connected","gap","hi_rank","lo_rank","avg_rank"] if k in dbg})
    print("board:", {k:dbg[k] for k in ["board_cnt","pairs","trips","quads","max_suit_count","rank_span","consec_run_len"] if k in dbg})
    print("vector size:", len(x))
