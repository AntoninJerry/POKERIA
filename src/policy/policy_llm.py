from src.state.builder import build_state
from src.featurize.features import featurize
from src.policy.ollama_client import ask_policy

def recommend():
    """
    Renvoie (raw_action_dict, dbg_meta_dict)
    - Garde-fou: si Héro <2 cartes -> action 'none'.
    """
    st = build_state()

    # Pas de cartes héro -> aucune action
    if len(st.hero_cards) < 2:
        dbg = {
            "street": 0, "position": "unknown", "spr": 0.0,
            "hero_cards": st.hero_cards, "board_cards": st.community_cards,
            "pot_size": float(st.pot_size), "hero_stack": float(st.hero_stack),
            "to_call": float(st.to_call),
        }
        return {"action":"none","reason":"hero cards missing"}, dbg

    x, names, dbg = featurize(st)
    dbg["hero_cards"]  = st.hero_cards
    dbg["board_cards"] = st.community_cards
    dbg["pot_size"]    = float(st.pot_size)
    dbg["hero_stack"]  = float(st.hero_stack)
    dbg["to_call"]     = float(st.to_call)

    raw = ask_policy(x, dbg)  # dict (non normalisé)
    return raw, dbg
