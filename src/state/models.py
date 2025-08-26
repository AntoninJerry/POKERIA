from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class TableState:
    hero_cards: List[str] = field(default_factory=list)
    community_cards: List[str] = field(default_factory=list)
    pot_size: float = 0.0
    hero_stack: float = 0.0
    dealer_seat: Optional[int] = None
    hero_seat: Optional[int] = None
    seats_n: int = 6
    stacks: Dict[int, float] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    to_call: float = 0.0    # <<< montant à payer (€, si dispo)
