from src.state.builder import build_state

if __name__=="__main__":
    st = build_state()
    print("=== TABLE STATE ===")
    print("Hero cards     :", st.hero_cards)
    print("Community      :", st.community_cards)
    print("Pot size       :", st.pot_size)
    print("Hero stack     :", st.hero_stack)
    print("Dealer seat    :", st.dealer_seat)
    print("Hero seat      :", st.hero_seat)
