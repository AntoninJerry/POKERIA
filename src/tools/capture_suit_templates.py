# src/tools/capture_suit_templates.py
import os
import cv2
from pathlib import Path
from typing import Tuple, Optional, Dict

# Forcer plein écran (même logique que les previews fullscreen)
os.environ["POKERIA_WINDOWED"] = "0"

from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM
from src.capture.screen import capture_table

OUT_DIR = Path(os.getenv("POKERIA_SUITS_DIR", "assets/templates/suits"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

CARDS = [
    "hero_card_left", "hero_card_right",
    "board_card_1", "board_card_2", "board_card_3", "board_card_4", "board_card_5"
]

HELP = """
Touches:
  Navigation cartes : n = carte suivante,  ESC = quitter
  Sauvegarde patch  : h=♥   d=♦   s=♠   c=♣
  Ajuster suit_rel (cadre vert):
    Flèches  : déplacer (pas en px)
    [ / ]    : diminuer / augmenter la largeur
    - / +    : diminuer / augmenter la hauteur
    , / .    : pas -- / pas ++   (1..20 px)
    g        : activer/désactiver l’assombrissement autour
    p        : imprimer suit_rel (à coller dans le YAML)
    h        : réafficher cette aide
"""

# Codes flèches (cv2.waitKeyEx sous Windows)
KEY_LEFT, KEY_UP, KEY_RIGHT, KEY_DOWN = 2424832, 2490368, 2555904, 2621440


def rel_to_abs(rel, W: int, H: int) -> Tuple[int, int, int, int]:
    """[rx,ry,rw,rh] relatif -> (x,y,w,h) absolu, clampé dans [0,W/H)."""
    rx, ry, rw, rh = rel
    x = int(rx * W); y = int(ry * H)
    w = max(1, int(rw * W)); h = max(1, int(rh * H))
    x = max(0, min(x, W - 1)); y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x)); h = max(1, min(h, H - y))
    return x, y, w, h


def abs_to_rel(parent_x: int, parent_y: int, parent_w: int, parent_h: int,
               rx: int, ry: int, rw: int, rh: int) -> Tuple[float, float, float, float]:
    """Convertit un cadre absolu (rx,ry,rw,rh) en relatif AU CADRE PARENT (carte)."""
    pw = max(1, parent_w); ph = max(1, parent_h)
    return (
        (rx - parent_x) / pw,
        (ry - parent_y) / ph,
        rw / pw,
        rh / ph,
    )


def clamp_in(parent_x: int, parent_y: int, parent_w: int, parent_h: int,
             rx: int, ry: int, rw: int, rh: int) -> Tuple[int, int, int, int]:
    """Assure que le cadre (rx,ry,rw,rh) reste dans le parent (carte)."""
    rx = max(parent_x, min(rx, parent_x + parent_w - 1))
    ry = max(parent_y, min(ry, parent_y + parent_h - 1))
    rw = max(1, min(rw, parent_x + parent_w - rx))
    rh = max(1, min(rh, parent_y + parent_h - ry))
    return rx, ry, rw, rh


def draw_highlight(bgr, rx: int, ry: int, rw: int, rh: int, shade_on: bool = True):
    vis = bgr.copy()
    if shade_on:
        overlay = vis.copy()
        # assombrir tout
        cv2.rectangle(overlay, (0, 0), (vis.shape[1], vis.shape[0]), (0, 0, 0), -1)
        # ré-éclaircir la zone de focus (on “inhibe” le noir au même endroit)
        cv2.rectangle(overlay, (rx, ry), (rx + rw, ry + rh), (0, 0, 0), -1)
        vis = cv2.addWeighted(vis, 0.35, overlay, 0.65, 0)
    return vis


def show_zoom(patch_bgr, title: str = "suit_patch_zoom", factor: int = 3):
    zoom = cv2.resize(
        patch_bgr,
        (patch_bgr.shape[1] * factor, patch_bgr.shape[0] * factor),
        interpolation=cv2.INTER_NEAREST,
    )
    cv2.rectangle(zoom, (0, 0), (zoom.shape[1] - 1, zoom.shape[0] - 1), (0, 255, 0), 2)
    cv2.imshow(title, zoom)


def main():
    print(HELP)
    cfg = load_room_config(ACTIVE_ROOM)
    i = 0
    step = 2
    shade_on = True

    cv2.namedWindow("table", cv2.WINDOW_NORMAL)
    cv2.namedWindow("suit_patch", cv2.WINDOW_NORMAL)
    cv2.namedWindow("suit_patch_zoom", cv2.WINDOW_NORMAL)

    while True:
        # Capture table (RGB)
        table = capture_table(get_table_roi(ACTIVE_ROOM))
        H, W = table.shape[:2]

        # Carte courante
        name = CARDS[i % len(CARDS)]
        node = (cfg.get("rois_hint", {}) or {}).get(name, {})
        if not node or "rel" not in node:
            print(f"[WARN] ROI 'rel' manquante pour {name} → n pour passer.")
            i += 1
            continue

        # Cadre carte (absolu)
        cx, cy, cw, ch = rel_to_abs(node["rel"], W, H)

        # suit_rel (relatif à la carte). Valeur par défaut raisonnable si manquant.
        suit_rel = node.get("suit_rel", [0.02, 0.02, 0.52, 0.56])
        sx_rel, sy_rel, sw_rel, sh_rel = suit_rel
        sx, sy, sw, sh = rel_to_abs([sx_rel, sy_rel, sw_rel, sh_rel], cw, ch)
        sx += cx; sy += cy
        sx, sy, sw, sh = clamp_in(cx, cy, cw, ch, sx, sy, sw, sh)

        # Boucle d’ajustement / capture pour CETTE carte
        while True:
            vis = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)
            vis = draw_highlight(vis, sx, sy, sw, sh, shade_on)

            # cadres : carte (jaune), suit (vert)
            cv2.rectangle(vis, (cx, cy), (cx + cw, cy + ch), (0, 255, 255), 2)
            cv2.rectangle(vis, (sx, sy), (sx + sw, sy + sh), (0, 255, 0), 2)

            # infos
            srel_now = abs_to_rel(cx, cy, cw, ch, sx, sy, sw, sh)
            info = f"{name}  suit_rel=[{srel_now[0]:.6f},{srel_now[1]:.6f},{srel_now[2]:.6f},{srel_now[3]:.6f}]  step={step}px"
            cv2.putText(vis, info, (max(8, cx + 3), max(20, cy - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

            # patch pour enregistrement / zoom
            patch = table[sy:sy + sh, sx: sx + sw].copy()
            patch_bgr = cv2.cvtColor(patch, cv2.COLOR_RGB2BGR)

            cv2.imshow("table", vis)
            cv2.imshow("suit_patch", patch_bgr)
            show_zoom(patch_bgr, "suit_patch_zoom", factor=3)

            k = cv2.waitKeyEx(0) & 0xFFFFFFFF

            if k == 27:  # ESC -> quitter
                cv2.destroyAllWindows()
                return

            elif k == ord('n'):  # carte suivante
                node["suit_rel"] = list(srel_now)
                cfg["rois_hint"][name] = node
                i += 1
                break

            # Déplacements
            elif k in (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN):
                if k == KEY_LEFT:  sx -= step
                if k == KEY_RIGHT: sx += step
                if k == KEY_UP:    sy -= step
                if k == KEY_DOWN:  sy += step
                sx, sy, sw, sh = clamp_in(cx, cy, cw, ch, sx, sy, sw, sh)

            # Redimensionnements
            elif k == ord('['):    # largeur --
                sw -= step; sx, sy, sw, sh = clamp_in(cx, cy, cw, ch, sx, sy, max(1, sw), sh)
            elif k == ord(']'):    # largeur ++
                sw += step; sx, sy, sw, sh = clamp_in(cx, cy, cw, ch, sx, sy, sw, sh)
            elif k in (ord('-'), ord('_')):  # hauteur --
                sh -= step; sx, sy, sw, sh = clamp_in(cx, cy, cw, ch, sx, sy, sw, max(1, sh))
            elif k in (ord('+'), ord('=')):  # hauteur ++
                sh += step; sx, sy, sw, sh = clamp_in(cx, cy, cw, ch, sx, sy, sw, sh)

            # Pas
            elif k == ord(','):
                step = max(1, step - 1)
            elif k == ord('.'):
                step = min(20, step + 1)

            # Ombre / print / aide
            elif k == ord('g'):
                shade_on = not shade_on
            elif k == ord('p'):
                srel_now = abs_to_rel(cx, cy, cw, ch, sx, sy, sw, sh)
                print(f"{name}  suit_rel: [{srel_now[0]:.6f}, {srel_now[1]:.6f}, {srel_now[2]:.6f}, {srel_now[3]:.6f}]")
            elif k == ord('h'):
                print(HELP)

            # Sauvegarde patch (♥♦♠♣)
            elif k in (ord('h'), ord('d'), ord('s'), ord('c')):
                lab = chr(k).lower()
                existing = sorted(OUT_DIR.glob(f"{lab}_*.png"))
                idx = len(existing) + 1
                out = OUT_DIR / f"{lab}_{idx:02d}.png"
                cv2.imwrite(str(out), patch_bgr)
                print("💾 saved", out)
                # On avance à la carte suivante pour varier les samples
                node["suit_rel"] = list(srel_now)
                cfg["rois_hint"][name] = node
                i += 1
                break

            else:
                print("… touche inconnue :", k, " | " + HELP)

    cv2.destroyAllWindows()
    print("Bye.")


if __name__ == "__main__":
    main()
