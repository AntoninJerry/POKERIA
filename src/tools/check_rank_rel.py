# src/tools/check_rank_rel.py
from src.config.settings import load_room_config, ACTIVE_ROOM
CARDS = ["hero_card_left","hero_card_right","board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"]

def main():
    cfg = load_room_config(ACTIVE_ROOM)
    rois = (cfg.get("rois_hint") or {})
    print("ACTIVE_ROOM:", ACTIVE_ROOM)
    for name in CARDS:
        node = (rois.get(name) or {})
        has_rel = "rel" in node
        has_rank = "rank_rel" in node
        print(f"{name:14}  rel={has_rel}  rank_rel={has_rank}  {node.get('rank_rel')}")

if __name__ == "__main__":
    main()
