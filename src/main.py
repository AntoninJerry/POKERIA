# src/main.py
from __future__ import annotations
import os, sys, argparse

def _force_fullscreen_mode():
    # Toujours plein écran pour la V1
    os.environ.setdefault("POKERIA_WINDOWED", "0")

def _precheck():
    from src.config.settings import ACTIVE_ROOM, load_room_config, get_table_roi
    cfg = load_room_config(ACTIVE_ROOM)
    rect = get_table_roi(ACTIVE_ROOM)
    roi = f"{rect.w}x{rect.h}@({rect.x},{rect.y})"
    print(f"[PRECHECK] room={cfg.get('room', ACTIVE_ROOM)}  table_roi={roi}")

def cmd_overlay(_args):
    # HUD temps réel (version écran plein)
    from src.ui.overlay import run as run_overlay
    run_overlay()

def cmd_preview_rois(_args):
    # Aperçu des cadrages (plein écran/YAML)
    from src.tools.preview_rois_fullscreen import main as tool_main
    tool_main()

def cmd_ocr_smoke(_args):
    # Lecture pot/stack (montants)
    from src.tools.ocr_smoke import main as tool_main
    tool_main()

def cmd_cards_smoke(args):
    # Lecture cartes (héros + board)
    sys.argv = ["ocr_cards_smoke.py"] + (["--show"] if args.show else [])
    from src.tools.ocr_cards_smoke import main as tool_main
    tool_main()

def cmd_state_smoke(_args):
    from src.tools.state_smoke import main as tool_main
    tool_main()

def cmd_features_smoke(_args):
    from src.tools.features_smoke import main as tool_main
    tool_main()

def cmd_policy_cli(_args):
    # Reco IA (Ollama) sur un état lu à l’instant
    from src.policy.policy_cli import main as tool_main
    tool_main()

def cmd_edit_rank_rel(_args):
    # Éditeur interactif pour rank_rel dans le YAML
    from src.tools.edit_rank_rel import main as tool_main
    tool_main()

def cmd_validate_rois(_args):
    # Validation bornes + snapshot annoté
    from src.tools.validate_rois import main as tool_main
    tool_main()

def build_parser():
    p = argparse.ArgumentParser(
        prog="pokeria",
        description="Pokeria – entrée unique (mode plein écran)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("overlay", help="Lancer l’overlay (HUD).").set_defaults(func=cmd_overlay)
    sub.add_parser("preview-rois", help="Aperçu des ROIs (plein écran).").set_defaults(func=cmd_preview_rois)
    sub.add_parser("ocr-smoke", help="Smoke OCR montants (pot/stack).").set_defaults(func=cmd_ocr_smoke)

    ps = sub.add_parser("cards-smoke", help="Smoke OCR cartes (héros + board).")
    ps.add_argument("--show", action="store_true", help="Afficher l’overlay debug des ROIs.")
    ps.set_defaults(func=cmd_cards_smoke)

    sub.add_parser("state-smoke", help="Construction d’état (TableState).").set_defaults(func=cmd_state_smoke)
    sub.add_parser("features-smoke", help="Calcul des features.").set_defaults(func=cmd_features_smoke)
    sub.add_parser("policy-cli", help="Reco IA (Ollama) en CLI.").set_defaults(func=cmd_policy_cli)
    sub.add_parser("edit-rank-rel", help="Éditer les rank_rel dans le YAML.").set_defaults(func=cmd_edit_rank_rel)
    sub.add_parser("validate-rois", help="Valider les ROIs (bornes, snapshot).").set_defaults(func=cmd_validate_rois)

    return p

def main():
    _force_fullscreen_mode()
    _precheck()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
