from typing import List, Tuple, Optional, Dict
import numpy as np

RANK_ORDER = "23456789TJQKA"
RANK_TO_VAL = {r: i+2 for i, r in enumerate(RANK_ORDER)}  # 2..14
VAL_TO_RANK = {v: r for r, v in RANK_TO_VAL.items()}
SUITS = "hdsc"  # h=♥, d=♦, s=♠, c=♣

def parse_card(card: str) -> Optional[Tuple[int, str]]:
    # "Ah" -> (14,'h'); tolère "10h" => "Th"
    if not card or len(card) < 2: return None
    r, s = card[0].upper(), card[-1].lower()
    if r == "1": r = "T"
    if r not in RANK_TO_VAL or s not in SUITS: return None
    return RANK_TO_VAL[r], s

def parse_cards(cards: List[str]) -> List[Tuple[int, str]]:
    out = []
    for c in cards:
        pc = parse_card(c)
        if pc: out.append(pc)
    return out

def onehot_card(card: str) -> np.ndarray:
    """52-dim one-hot: idx = rank_index*4 + suit_index (rank 2..A)."""
    v = np.zeros(52, dtype=np.float32)
    pc = parse_card(card)
    if not pc: return v
    r, s = pc
    ridx = (r - 2)  # 0..12
    sidx = SUITS.index(s)  # 0..3
    v[ridx * 4 + sidx] = 1.0
    return v

def hero_hand_feats(hero_cards: List[str]) -> Dict[str, float]:
    """Retourne des features basiques héros; zeros si <2 cartes."""
    cards = parse_cards(hero_cards)
    out = dict(is_pair=0.0, is_suited=0.0, is_connected=0.0, gap=0.0,
               hi_rank=0.0, lo_rank=0.0, avg_rank=0.0)
    if len(cards) < 2:
        return out
    (r1, s1), (r2, s2) = cards[0], cards[1]
    hi, lo = max(r1, r2), min(r1, r2)
    out["hi_rank"] = hi; out["lo_rank"] = lo; out["avg_rank"] = (hi + lo) / 2.0
    out["is_pair"] = 1.0 if r1 == r2 else 0.0
    out["is_suited"] = 1.0 if s1 == s2 else 0.0
    gap = abs(r1 - r2) - 1  # ex: 76 -> gap=0 (connecté), 75 -> 1
    gap = max(0, gap)
    out["gap"] = float(gap)
    out["is_connected"] = 1.0 if gap == 0 else 0.0
    return out

def board_feats(board_cards: List[str]) -> Dict[str, float]:
    """Texture board : paires, bicolore/monochrome, straight/flush draws (approx)."""
    cards = parse_cards(board_cards)
    ranks = [r for r, _ in cards]
    suits = [s for _, s in cards]

    out = {
        "board_cnt": float(len(cards)),
        "pairs": 0.0, "trips": 0.0, "quads": 0.0,
        "is_rainbow": 0.0, "is_two_tone": 0.0, "is_monotone": 0.0,
        "max_suit_count": 0.0,
        "rank_span": 0.0,  # max-min
        "consec_run_len": 0.0,  # max série consécutive
    }
    if not cards:
        return out

    # groupes rang
    from collections import Counter
    rc = Counter(ranks)
    counts = sorted(rc.values(), reverse=True)
    if counts:
        out["pairs"] = float(sum(1 for c in counts if c == 2))
        out["trips"] = 1.0 if 3 in counts else 0.0
        out["quads"] = 1.0 if 4 in counts else 0.0

    # couleurs
    sc = Counter(suits)
    max_suit = max(sc.values())
    out["max_suit_count"] = float(max_suit)
    if len(sc) == 1: out["is_monotone"] = 1.0
    elif len(sc) == 2: out["is_two_tone"] = 1.0
    else: out["is_rainbow"] = 1.0

    # span et run consécutif (A=14)
    rr = sorted(set(ranks))
    out["rank_span"] = float(max(rr) - min(rr)) if rr else 0.0
    # run max
    run, best = 1, 1
    for i in range(1, len(rr)):
        if rr[i] == rr[i-1] + 1: run += 1; best = max(best, run)
        else: run = 1
    out["consec_run_len"] = float(best)
    return out
