# src/tools/init_rank_rel_defaults.py
import os
import argparse
import time
from pathlib import Path
from typing import List, Dict, Any

import yaml  # PyYAML

# Forcer le mode plein écran par défaut (modifiable via --windowed)
os.environ.setdefault("POKERIA_WINDOWED", "0")

from src.config.settings import ACTIVE_ROOM  # on lit juste la room active


CARDS: List[str] = [
    "hero_card_left", "hero_card_right",
    "board_card_1", "board_card_2", "board_card_3", "board_card_4", "board_card_5"
]

# Valeur passe-partout : coin haut-gauche de la carte (rang), taille raisonnable
DEFAULT_RANK_REL = [0.05, 0.06, 0.32, 0.46]


def candidates_for(room: str) -> List[Path]:
    """Retourne une liste d'emplacements YAML probables pour la room."""
    bases: List[Path] = []
    env_dir = os.getenv("POKERIA_ROOMS_DIR")
    if env_dir:
        bases.append(Path(env_dir))
    bases += [
        Path("assets/rooms"),
        Path("assets/config/rooms"),
        Path("config/rooms"),
        Path("configs/rooms"),
        Path("src/config/rooms"),
    ]

    names = [
        f"{room}.yaml", f"{room}.yml",
        f"{room}_fullscreen.yaml", f"{room}_fullscreen.yml",
        f"{room}_windowed.yaml", f"{room}_windowed.yml",
        f"{room}-fullscreen.yaml", f"{room}-windowed.yaml",
    ]

    out: List[Path] = []
    seen = set()
    for base in bases:
        for name in names:
            p = base / name
            if p not in seen:
                out.append(p)
                seen.add(p)
    return out


def choose_yaml_path(room: str, windowed: bool) -> Path:
    """Choisit le YAML existant le plus plausible. Si aucun, propose un chemin standard à créer."""
    found: List[Path] = [p for p in candidates_for(room) if p.exists()]
    if found:
        def score(path: Path) -> int:
            s = 0
            n = path.name.lower()
            if windowed:
                if "windowed" in n: s += 3
                if "fullscreen" in n: s -= 2
            else:
                if "windowed" in n: s -= 2
                if "fullscreen" in n: s += 2
            if n.endswith(".yaml"): s += 1
            return s
        best = max(found, key=score)
        return best

    # Aucun fichier trouvé → on propose un chemin standard à créer
    base = Path(os.getenv("POKERIA_ROOMS_DIR") or "assets/rooms")
    base.mkdir(parents=True, exist_ok=True)
    name = f"{room}_windowed.yaml" if windowed else f"{room}_fullscreen.yaml"
    return base / name


def load_yaml(path: Path) -> Dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def write_yaml_with_backup(path: Path, data: Dict[str, Any]) -> Path:
    # sauvegarde .bak horodatée
    if path.exists():
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".{ts}.bak")
        backup.write_bytes(path.read_bytes())
        print(f"🧯 Backup créé: {backup}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return path


def ensure_rank_rel(cfg: Dict[str, Any], default_rank_rel: List[float], overwrite: bool) -> Dict[str, Any]:
    # S'assure que rois_hint existe
    if "rois_hint" not in cfg or not isinstance(cfg.get("rois_hint"), dict):
        cfg["rois_hint"] = {}
    rois = cfg["rois_hint"]

    added, kept, overwritten = 0, 0, 0
    for name in CARDS:
        node = rois.get(name) or {}
        have = "rank_rel" in node and isinstance(node["rank_rel"], (list, tuple)) and len(node["rank_rel"]) == 4
        if have and not overwrite:
            kept += 1
        else:
            if have and overwrite:
                overwritten += 1
            else:
                added += 1
            node["rank_rel"] = list(map(float, default_rank_rel))
        rois[name] = node

    print(f"Résumé: ajoutés={added}, conservés={kept}, écrasés={overwritten}")
    cfg["rois_hint"] = rois
    return cfg


def main():
    ap = argparse.ArgumentParser(description="Initialiser/mettre à jour rank_rel dans le YAML de la room active.")
    ap.add_argument("--room", default=ACTIVE_ROOM, help="Nom de la room (défaut: ACTIVE_ROOM)")
    ap.add_argument("--windowed", action="store_true", help="Cibler le YAML fenêtré (par défaut: fullscreen)")
    ap.add_argument("--overwrite", action="store_true", help="Écraser les rank_rel existants")
    ap.add_argument("--default", default="0.05,0.06,0.32,0.46", help="Valeur par défaut: rx,ry,rw,rh (relatifs)")
    args = ap.parse_args()

    # si --windowed, on force l'env en conséquence pour homogénéité
    os.environ["POKERIA_WINDOWED"] = "1" if args.windowed else "0"

    # parse la valeur par défaut
    try:
        default_rank_rel = [float(x.strip()) for x in args.default.split(",")]
        if len(default_rank_rel) != 4:
            raise ValueError
    except Exception:
        print("❌ --default doit contenir 4 nombres séparés par des virgules, ex: 0.05,0.06,0.32,0.46")
        return

    yaml_path = choose_yaml_path(args.room, windowed=args.windowed)
    print(f"Room: {args.room} | Mode: {'windowed' if args.windowed else 'fullscreen'}")
    print(f"YAML ciblé: {yaml_path.resolve()}")

    cfg = load_yaml(yaml_path)
    # assurer 'room'
    cfg.setdefault("room", args.room)

    cfg = ensure_rank_rel(cfg, default_rank_rel, overwrite=args.overwrite)
    written = write_yaml_with_backup(yaml_path, cfg)
    print(f"✅ rank_rel écrit dans: {written.resolve()}")
    print("➡️  Tu peux maintenant lancer:  python -m src.tools.preview_rank_ocr  (puis R pour recharger)")
    

if __name__ == "__main__":
    main()
