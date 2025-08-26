from collections import deque, Counter
from typing import Optional, Deque, Tuple, List

class FieldStabilizer:
    def __init__(self, k: int = 3):
        self.k = k
        self.buf: Deque[Tuple[Optional[str], float]] = deque(maxlen=k)
        self.last: Optional[str] = None

    def push(self, val: Optional[str], conf: float) -> Optional[str]:
        if val is None: conf = 0.0
        self.buf.append((val, conf))
        # vote majoritaire pondéré par conf
        cnt = Counter()
        for v,c in self.buf:
            if v: cnt[v] += 1 + c*0.5
        if not cnt: return self.last
        best, score = cnt.most_common(1)[0]
        # exige au moins 2 occurrences ou conf moyenne > 0.75
        occ = sum(1 for v,_ in self.buf if v==best)
        avgc = sum(c for v,c in self.buf if v==best)/max(1,occ)
        if occ >= 2 or avgc >= 0.75:
            self.last = best
        return self.last

class CardsStabilizer:
    def __init__(self, k: int = 3):
        self.hero = [FieldStabilizer(k), FieldStabilizer(k)]
        self.board = [FieldStabilizer(k) for _ in range(5)]

    def push_hero(self, two_cards: List[Tuple[Optional[str], float]]):
        out = []
        for i in range(2):
            val, conf = two_cards[i] if i<len(two_cards) else (None,0.0)
            out.append(self.hero[i].push(val, conf))
        return out

    def push_board(self, cards: List[Tuple[Optional[str], float]]):
        out = []
        for i in range(5):
            val, conf = cards[i] if i<len(cards) else (None,0.0)
            out.append(self.board[i].push(val, conf))
        return out
