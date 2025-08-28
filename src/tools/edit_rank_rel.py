# src/tools/edit_rank_rel.py
import os, time, argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import cv2
import yaml

# ---- Modes (FS par défaut) ----
os.environ.setdefault("POKERIA_WINDOWED", "0")

from src.config.settings import ACTIVE_ROOM, load_room_config, get_table_roi
from src.capture.screen import capture_table

CARDS: List[str] = [
    "hero_card_left", "hero_card_right",
    "board_card_1", "board_card_2", "board_card_3", "board_card_4", "board_card_5"
]

DEFAULT_RANK_REL = [0.05, 0.06, 0.32, 0.46]  # coin haut-gauche, zone raisonnable

# Codes flèches (Windows/WaitKeyEx)
KEY_LEFT, KEY_UP, KEY_RIGHT, KEY_DOWN = 2424832, 2490368, 2555904, 2621440

# ---------------- YAML utils ----------------
def candidates_for(room: str) -> List[Path]:
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
    out, seen = [], set()
    for base in bases:
        for name in names:
            p = base / name
            if p not in seen:
                out.append(p)
                seen.add(p)
    return out

def choose_yaml_path(room: str, windowed: bool) -> Path:
    found = [p for p in candidates_for(room) if p.exists()]
    if found:
        def score(path: Path) -> int:
            s, n = 0, path.name.lower()
            if windowed:
                if "windowed" in n: s += 3
                if "fullscreen" in n: s -= 2
            else:
                if "windowed" in n: s -= 2
                if "fullscreen" in n: s += 2
            if n.endswith(".yaml"): s += 1
            return s
        return max(found, key=score)
    base = Path(os.getenv("POKERIA_ROOMS_DIR") or "assets/rooms")
    base.mkdir(parents=True, exist_ok=True)
    return base / (f"{room}_windowed.yaml" if windowed else f"{room}_fullscreen.yaml")

def load_yaml(path: Path) -> Dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    return data if isinstance(data, dict) else {}

def write_yaml_with_backup(path: Path, data: Dict[str, Any]) -> Path:
    if path.exists():
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".{ts}.bak")
        backup.write_bytes(path.read_bytes())
        print(f"🧯 Backup: {backup}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return path

# ---------------- Geometry utils ----------------
def rel_to_abs(rel, W: int, H: int) -> Tuple[int,int,int,int]:
    rx, ry, rw, rh = rel
    x = int(rx*W); y = int(ry*H)
    w = max(1, int(rw*W)); h = max(1, int(rh*H))
    x = max(0, min(x, W-1)); y = max(0, min(y, H-1))
    w = max(1, min(w, W-x)); h = max(1, min(h, H-y))
    return x, y, w, h

def abs_to_rel(px: int, py: int, pw: int, ph: int, rx: int, ry: int, rw: int, rh: int) -> List[float]:
    pw = max(1, pw); ph = max(1, ph)
    return [
        (rx - px)/pw,
        (ry - py)/ph,
        rw/pw,
        rh/ph,
    ]

def clamp_in(px: int, py: int, pw: int, ph: int, rx: int, ry: int, rw: int, rh: int) -> Tuple[int,int,int,int]:
    rx = max(px, min(rx, px + pw - 1))
    ry = max(py, min(ry, py + ph - 1))
    rw = max(1, min(rw, px + pw - rx))
    rh = max(1, min(rh, py + ph - ry))
    return rx, ry, rw, rh

def draw_highlight(bgr, rx: int, ry: int, rw: int, rh: int, shade_on: bool):
    vis = bgr.copy()
    if shade_on:
        overlay = vis.copy()
        cv2.rectangle(overlay, (0,0), (vis.shape[1], vis.shape[0]), (0,0,0), -1)
        cv2.rectangle(overlay, (rx,ry), (rx+rw, ry+rh), (0,0,0), -1)
        vis = cv2.addWeighted(vis, 0.35, overlay, 0.65, 0)
    return vis

def show_zoom(patch_bgr, title="rank_patch_zoom", factor=3):
    zoom = cv2.resize(patch_bgr, (patch_bgr.shape[1]*factor, patch_bgr.shape[0]*factor), interpolation=cv2.INTER_NEAREST)
    cv2.rectangle(zoom, (0,0), (zoom.shape[1]-1, zoom.shape[0]-1), (0,255,0), 2)
    cv2.imshow(title, zoom)

# ---------------- Editor ----------------
def main():
    ap = argparse.ArgumentParser(description="Éditeur interactif des rank_rel avec sauvegarde directe dans le YAML.")
    ap.add_argument("--room", default=ACTIVE_ROOM, help="Room (défaut: ACTIVE_ROOM)")
    ap.add_argument("--windowed", action="store_true", help="Cible le YAML fenêtré (défaut: fullscreen)")
    ap.add_argument("--yaml", type=str, default=None, help="Chemin YAML explicite (outrepasse la détection)")
    ap.add_argument("--default", default="0.05,0.06,0.32,0.46", help="rank_rel par défaut si manquant (rx,ry,rw,rh)")
    ap.add_argument("--autosave", action="store_true", help="Sauvegarde auto à chaque 'n' (carte suivante)")
    args = ap.parse_args()

    # Forcer l'env pour cohérence capture <-> YAML
    os.environ["POKERIA_WINDOWED"] = "1" if args.windowed else "0"
    mode = "WIN" if args.windowed else "FS"

    # YAML ciblé
    yaml_path = Path(args.yaml) if args.yaml else choose_yaml_path(args.room, windowed=args.windowed)
    print(f"Room={args.room}  Mode={mode}  YAML={yaml_path.resolve()}")

    # Valeur par défaut
    try:
        default_rank_rel = [float(x.strip()) for x in args.default.split(",")]
        assert len(default_rank_rel) == 4
    except Exception:
        print("❌ --default doit être 'rx,ry,rw,rh' (4 nombres). Ex: 0.05,0.06,0.32,0.46")
        return

    # Charger YAML (fichier) + cfg live (pour cohérence si ailleurs)
    cfg_file = load_yaml(yaml_path)
    cfg_live = load_room_config(args.room)  # utilisé pour read-only si besoin

    # S'assurer de la structure
    cfg_file.setdefault("room", args.room)
    cfg_file.setdefault("rois_hint", {})
    rois = cfg_file["rois_hint"]

    # Fenêtres
    cv2.namedWindow("RankRel Editor ["+mode+"]", cv2.WINDOW_NORMAL)
    cv2.namedWindow("rank_patch", cv2.WINDOW_NORMAL)
    cv2.namedWindow("rank_patch_zoom", cv2.WINDOW_NORMAL)

    i = 0
    step = 2
    shade_on = True
    changed = False

    while True:
        # Capture table à chaque tour (suit déplacements)
        rect = get_table_roi(args.room)
        rgb = capture_table(rect)
        if rgb is None:
            print("❌ Impossible de capturer la table.")
            break
        H, W = rgb.shape[:2]
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        name = CARDS[i % len(CARDS)]
        node = rois.get(name) or {}
        if "rel" not in node:
            print(f"[WARN] '{name}' n'a pas de 'rel' → n pour passer")
            i += 1
            continue

        # Cadre carte
        cx, cy, cw, ch = rel_to_abs(node["rel"], W, H)

        # rank_rel courant (ou défaut)
        rank_rel = node.get("rank_rel", list(default_rank_rel))
        rx_rel, ry_rel, rw_rel, rh_rel = rank_rel
        rx, ry, rw, rh = rel_to_abs([rx_rel, ry_rel, rw_rel, rh_rel], cw, ch)
        rx += cx; ry += cy
        rx, ry, rw, rh = clamp_in(cx, cy, cw, ch, rx, ry, rw, rh)

        # Boucle carte
        while True:
            vis = draw_highlight(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), rx, ry, rw, rh, shade_on)
            # cadres
            cv2.rectangle(vis, (cx, cy), (cx+cw, cy+ch), (0,255,255), 2)      # carte (jaune)
            cv2.rectangle(vis, (rx, ry), (rx+rw, ry+rh), (0,255,0), 2)        # rank (vert)

            # infos
            rrel_now = abs_to_rel(cx, cy, cw, ch, rx, ry, rw, rh)
            info = f"{name}  rank_rel=[{rrel_now[0]:.6f},{rrel_now[1]:.6f},{rrel_now[2]:.6f},{rrel_now[3]:.6f}]  step={step}px"
            cv2.putText(vis, info, (max(8, cx+3), max(20, cy-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 2)

            # patch & zoom
            patch_rgb = rgb[ry:ry+rh, rx:rx+rw].copy()
            patch_bgr = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2BGR)
            cv2.imshow("RankRel Editor ["+mode+"]", vis)
            cv2.imshow("rank_patch", patch_bgr)
            show_zoom(patch_bgr, factor=3)

            k = cv2.waitKeyEx(0) & 0xFFFFFFFF

            if k == 27:  # ESC
                # Si des modifs en mémoire non sauvegardées, proposer une dernière sauvegarde
                cv2.destroyAllWindows()
                return

            elif k == ord('n'):  # carte suivante
                # autosave si demandé
                if args.autosave:
                    node["rank_rel"] = list(rrel_now)
                    rois[name] = node
                    cfg_file["rois_hint"] = rois
                    write_yaml_with_backup(yaml_path, cfg_file)
                    print(f"💾 Sauvé {name} → YAML")
                    changed = False
                i += 1
                break

            elif k == ord('b'):  # carte précédente
                if args.autosave and changed:
                    node["rank_rel"] = list(rrel_now)
                    rois[name] = node
                    cfg_file["rois_hint"] = rois
                    write_yaml_with_backup(yaml_path, cfg_file)
                    print(f"💾 Sauvé {name} → YAML")
                    changed = False
                i = (i - 1) % len(CARDS)
                break

            # Déplacements
            elif k in (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN):
                if k == KEY_LEFT:  rx -= step
                if k == KEY_RIGHT: rx += step
                if k == KEY_UP:    ry -= step
                if k == KEY_DOWN:  ry += step
                rx, ry, rw, rh = clamp_in(cx, cy, cw, ch, rx, ry, rw, rh); changed = True

            # Redim
            elif k == ord('['):    # largeur --
                rw -= step; rx, ry, rw, rh = clamp_in(cx, cy, cw, ch, rx, ry, max(1,rw), rh); changed = True
            elif k == ord(']'):    # largeur ++
                rw += step; rx, ry, rw, rh = clamp_in(cx, cy, cw, ch, rx, ry, rw, rh); changed = True
            elif k in (ord('-'), ord('_')):  # hauteur --
                rh -= step; rx, ry, rw, rh = clamp_in(cx, cy, cw, ch, rx, ry, rw, max(1,rh)); changed = True
            elif k in (ord('='), ord('+')):  # hauteur ++
                rh += step; rx, ry, rw, rh = clamp_in(cx, cy, cw, ch, rx, ry, rw, rh); changed = True

            # Pas
            elif k == ord(','): step = max(1, step-1)
            elif k == ord('.'): step = min(20, step+1)

            # Options
            elif k == ord('g'): shade_on = not shade_on
            elif k == ord('p'):
                print(f"{name}  rank_rel: [{rrel_now[0]:.6f}, {rrel_now[1]:.6f}, {rrel_now[2]:.6f}, {rrel_now[3]:.6f}]")
            elif k == ord('r'):
                # recharger depuis le fichier YAML (si édité à côté)
                cfg_file = load_yaml(yaml_path)
                cfg_file.setdefault("rois_hint", {})
                rois = cfg_file["rois_hint"]
                node = rois.get(name) or node  # garder au moins rel
                changed = False
                print("🔄 YAML rechargé.")

            elif k == ord('s'):  # SAUVEGARDER CETTE CARTE
                node["rank_rel"] = list(rrel_now)
                rois[name] = node
                cfg_file["rois_hint"] = rois
                write_yaml_with_backup(yaml_path, cfg_file)
                print(f"💾 Sauvé {name} → {yaml_path}")
                changed = False

            elif k == ord('h'):
                print("""
Raccourcis:
  n      : carte suivante         b : carte précédente
  flèches: déplacer               [ ] : largeur - / +
  - / +  : hauteur - / +          , . : pas - / +
  s      : sauvegarder cette carte (écrit dans le YAML avec backup)
  r      : recharger le YAML      g : ombrage ON/OFF
  p      : imprimer rank_rel      ESC : quitter
  --autosave (option) : sauvegarde auto à chaque 'n' / 'b'
""")

if __name__ == "__main__":
    main()
