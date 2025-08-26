import time, cv2
from src.state.builder import build_state
from src.state.stabilizer import CardsStabilizer

def main():
    stab = CardsStabilizer(k=3)
    while True:
        st = build_state()  # lit une fois table
        # on ne récupère pas les confiances depuis builder -> on met 0.8 si non None
        hero_stab = stab.push_hero([(st.hero_cards[0] if len(st.hero_cards)>0 else None, 0.8),
                                    (st.hero_cards[1] if len(st.hero_cards)>1 else None, 0.8)])
        board_stab = stab.push_board([(st.community_cards[i] if i<len(st.community_cards) else None, 0.8) for i in range(5)])

        print(f"Hero live: {st.hero_cards}  -> stable: {hero_stab}")
        print(f"Board live: {st.community_cards} -> stable: {board_stab}")
        print(f"Pot={st.pot_size}  Stack={st.hero_stack}  Dealer={st.dealer_seat}")
        print("-"*60)
        if cv2.waitKey(1) & 0xFF == 27: break
        time.sleep(0.6)

if __name__ == "__main__":
    main()
