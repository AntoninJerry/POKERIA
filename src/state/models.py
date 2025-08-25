from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class TableState:
    hero_cards: List[str] = field(default_factory=list)      # ex: ["Ah","Kd"]
    community_cards: List[str] = field(default_factory=list) # flop/turn/river
    pot_size: float = 0.0
    hero_stack: float = 0.0
    dealer_seat: Optional[int] = None   # 0..N-1 (btn seat)
    hero_seat: Optional[int] = None     # index du siège du héros
    seats_n: int = 6
    # optionnel: dictionnaires
    stacks: Dict[int, float] = field(default_factory=dict)   # seat->stack
    actions: List[str] = field(default_factory=list)         # logs bruts
