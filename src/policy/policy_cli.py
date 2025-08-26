import os, time, argparse
from src.policy.policy_llm import recommend
from src.policy.postprocess import finalize_action
from src.policy.logger import append_decision

def main():
    ap = argparse.ArgumentParser(description="Pokeria policy CLI (Ollama)")
    ap.add_argument("--watch", action="store_true", help="boucle continue")
    ap.add_argument("--interval", type=float, default=1.0, help="pause entre itérations (s)")
    ap.add_argument("--model", default=os.getenv("OLLAMA_MODEL","llama3.1:8b"), help="modèle Ollama")
    args = ap.parse_args()

    def step():
        raw, dbg = recommend()               # brut LLM ou guard
        dec = finalize_action(raw, dbg)      # normalisé & sized
        append_decision(args.model, dbg, dec, raw)
        print(f"[{dbg.get('position','?')}] street={dbg.get('street')} spr={dbg.get('spr'):.2f} "
              f"hand={dbg.get('hero_cards')} board={dbg.get('board_cards')}  -> {dec}")

    if args.watch:
        while True:
            try: step()
            except Exception as e: print("❌ erreur policy:", repr(e))
            time.sleep(max(0.1, args.interval))
    else:
        step()

if __name__ == "__main__":
    main()
