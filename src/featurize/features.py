from typing import Dict, List, Tuple, Optional
import numpy as np
from src.state.models import TableState
from src.featurize.cards_utils import onehot_card, hero_hand_feats, board_feats, SUITS

def street_from_board(n: int) -> int:
    # 0: preflop, 1: flop (3), 2: turn (4), 3: river (5)
    return {0:0, 1:1, 2:1, 3:1, 4:2, 5:3}.get(n, 0)

def position_label(seats_n: int, dealer_seat: Optional[int], hero_seat: Optional[int]) -> str:
    """
    Map basique en 6-max (5-max/4-max se compriment).
    On suppose hero_seat=0 (en bas) si inconnu.
    """
    if hero_seat is None: hero_seat = 0
    if dealer_seat is None: return "unknown"
    rel = (hero_seat - dealer_seat) % max(1, seats_n or 6)
    # 6-max: BTN=0, SB=1, BB=2, UTG=3, MP=4, CO=5 (relatif depuis BTN)
    labels_6 = ["BTN", "SB", "BB", "UTG", "MP", "CO"]
    if seats_n and seats_n <= 3:
        labels_3 = ["BTN", "SB", "BB"]
        return labels_3[rel % 3]
    if seats_n and seats_n == 4:
        labels_4 = ["BTN", "SB", "BB", "UTG"]
        return labels_4[rel % 4]
    if seats_n and seats_n == 5:
        labels_5 = ["BTN", "SB", "BB", "UTG", "CO"]
        return labels_5[rel % 5]
    return labels_6[rel % 6]

def spr(hero_stack: float, pot_size: float) -> float:
    # Stack-to-Pot Ratio (approx avec stack héro si on n’a pas l’effectif)
    p = max(0.01, float(pot_size))
    return float(hero_stack) / p

def featurize(state: TableState) -> Tuple[np.ndarray, List[str], Dict[str, float]]:
    """
    Retourne (vecteur numpy, noms, dict) — dict lisible pour debug.
    """
    # --- scalaires
    street = street_from_board(len(state.community_cards))
    pos = position_label(state.seats_n, state.dealer_seat, state.hero_seat)
    pos_onehot_names = ["POS_BTN","POS_SB","POS_BB","POS_UTG","POS_MP","POS_CO","POS_UNKNOWN"]
    pos_map = {"BTN":0,"SB":1,"BB":2,"UTG":3,"MP":4,"CO":5,"unknown":6}
    pos_oh = np.zeros(len(pos_onehot_names), dtype=np.float32)
    pos_oh[pos_map.get(pos,6)] = 1.0

    spr_val = spr(state.hero_stack, state.pot_size)

    # --- héro
    hero_oh = np.zeros(104, dtype=np.float32)  # 2 cartes * 52
    if len(state.hero_cards) >= 1: hero_oh[0:52]   = onehot_card(state.hero_cards[0])
    if len(state.hero_cards) >= 2: hero_oh[52:104] = onehot_card(state.hero_cards[1])
    hfeat = hero_hand_feats(state.hero_cards)

    # --- board
    bfeat = board_feats(state.community_cards)
    board_oh = np.zeros(52*5, dtype=np.float32)
    for i, c in enumerate(state.community_cards[:5]):
        board_oh[i*52:(i+1)*52] = onehot_card(c)

    # --- assemblage
    scalars = np.array([
        float(state.pot_size),
        float(state.hero_stack),
        float(street),
        float(spr_val),
    ], dtype=np.float32)

    hvec = np.array([
        hfeat["is_pair"], hfeat["is_suited"], hfeat["is_connected"],
        hfeat["gap"], hfeat["hi_rank"], hfeat["lo_rank"], hfeat["avg_rank"],
    ], dtype=np.float32)

    bvec = np.array([
        bfeat["board_cnt"], bfeat["pairs"], bfeat["trips"], bfeat["quads"],
        bfeat["is_rainbow"], bfeat["is_two_tone"], bfeat["is_monotone"],
        bfeat["max_suit_count"], bfeat["rank_span"], bfeat["consec_run_len"],
    ], dtype=np.float32)

    x = np.concatenate([scalars, pos_oh, hvec, bvec, hero_oh, board_oh], axis=0)

    names = (
        ["pot_size","hero_stack","street","spr"]
        + pos_onehot_names
        + ["H_is_pair","H_is_suited","H_is_connected","H_gap","H_hi_rank","H_lo_rank","H_avg_rank"]
        + ["B_cnt","B_pairs","B_trips","B_quads","B_rainbow","B_two_tone","B_monotone",
           "B_max_suit","B_rank_span","B_consec_run"]
        + [f"H1_{i}" for i in range(52)] + [f"H2_{i}" for i in range(52)]
        + [f"B{i+1}_{j}" for i in range(5) for j in range(52)]
    )

    # dict lisible (debug)
    dbg = {
        "street": street,
        "position": pos,
        "spr": float(spr_val),
        **{k: float(v) for k, v in hfeat.items()},
        **{k: float(v) for k, v in bfeat.items()},
    }
    return x, names, dbg
