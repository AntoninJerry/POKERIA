# src/tools/capture_rank_templates.py
import os, cv2
from pathlib import Path
from src.config.settings import load_room_config, get_table_roi, ACTIVE_ROOM
from src.capture.screen import capture_table

os.environ["POKERIA_WINDOWED"] = "0"

OUT_DIR = Path(os.getenv("POKERIA_RANKS_DIR", "assets/templates/ranks"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

CARDS = [
    "hero_card_left","hero_card_right",
    "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"
]

HELP = """
Touches:
  Navigation cartes: n = carte suivante, ESC = quitter
  Sauvegarde échantillon: A K Q J T 9 8 7 6 5 4 3 2 (sur la carte affichée)
  Ajuster rank_rel (cadre vert):
    Flèches  : déplacer (par défaut 2 px)
    [ / ]    : diminuer / augmenter la largeur
    - / +    : diminuer / augmenter la hauteur
    , / .    : baisser / augmenter le pas (1..20 px)
    g        : activer/désactiver l’assombrissement autour
    p        : afficher rank_rel actuel (à coller dans le YAML)
    h        : réafficher cette aide
"""

# Codes des flèches (Windows / waitKeyEx)
KEY_LEFT, KEY_UP, KEY_RIGHT, KEY_DOWN = 2424832, 2490368, 2555904, 2621440

def rel_to_abs(rel, W, H):
    rx, ry, rw, rh = rel
    x = int(rx * W);  y = int(ry * H)
    w = max(1, int(rw * W));  h = max(1, int(rh * H))
    return x, y, w, h

def abs_to_rel(x, y, w, h, rx, ry, rw, rh):
    # retourne rank_rel (relatif AU CADRE DE LA CARTE, pas à la table)
    return [
        (rx - x) / max(1, w),
        (ry - y) / max(1, h),
        rw / max(1, w),
        rh / max(1, h),
    ]

def clamp_rank(x, y, w, h, rx, ry, rw, rh):
    # maintien le cadre vert DANS le cadre jaune
    rx = max(x, min(rx, x + w - 1))
    ry = max(y, min(ry, y + h - 1))
    rw = max(1, min(rw, x + w - rx))
    rh = max(1, min(rh, y + h - ry))
    return rx, ry, rw, rh

def draw_highlight(base_bgr, rx, ry, rw, rh, shade_on=True):
    vis = base_bgr.copy()
    if shade_on:
        overlay = vis.copy()
        # assombrir tout
        cv2.rectangle(overlay, (0, 0), (vis.shape[1], vis.shape[0]), (0, 0, 0), -1)
        # ré-éclaircir la zone verte
        cv2.rectangle(overlay, (rx, ry), (rx + rw, ry + rh), (0, 0, 0), -1)
        vis = cv2.addWeighted(vis, 0.35, overlay, 0.65, 0)
    # cadre jaune = carte entière
    return vis

def show_zoom(patch_bgr, title="rank_patch_zoom", factor=3):
    # zoom x3 pour viser les bords
    zoom = cv2.resize(patch_bgr, (patch_bgr.shape[1]*factor, patch_bgr.shape[0]*factor), interpolation=cv2.INTER_NEAREST)
    # cadre vert autour du patch pour le contraste
    cv2.rectangle(zoom, (0, 0), (zoom.shape[1]-1, zoom.shape[0]-1), (0, 255, 0), 2)
    cv2.imshow(title, zoom)

def main():
    print(HELP)
    cfg = load_room_config(ACTIVE_ROOM)
    i = 0
    step = 2           # pas en pixels pour ajustements
    shade_on = True    # assombrissement autour du cadre vert

    cv2.namedWindow("table", cv2.WINDOW_NORMAL)
    cv2.namedWindow("rank_patch", cv2.WINDOW_NORMAL)
    cv2.namedWindow("rank_patch_zoom", cv2.WINDOW_NORMAL)

    while True:
        table = capture_table(get_table_roi(ACTIVE_ROOM))  # attendu en RGB
        H, W = table.shape[:2]

        name = CARDS[i % len(CARDS)]
        node = (cfg.get("rois_hint", {}) or {}).get(name, {})
        if not node or "rel" not in node:
            i += 1
            continue

        # cadre "carte" (jaune)
        x, y, w, h = rel_to_abs(node["rel"], W, H)

        # cadre "rang" (vert) relatif à la carte
        rank_rel = node.get("rank_rel", [0.02, 0.02, 0.52, 0.56])
        rx, ry, rw, rh = rel_to_abs(rank_rel, w, h)
        rx, ry = x + rx, y + ry  # passer en coords table
        rx, ry, rw, rh = clamp_rank(x, y, w, h, rx, ry, rw, rh)

        # boucle d'ajustement / capture pour CETTE carte
        while True:
            # visuel table (BGR pour OpenCV) + surbrillance
            vis = cv2.cvtColor(table, cv2.COLOR_RGB2BGR)
            vis = draw_highlight(vis, rx, ry, rw, rh, shade_on)

            # cadres
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 255), 2)     # carte = jaune
            cv2.rectangle(vis, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 2) # rang = vert

            # petit texte d’info
            rr = abs_to_rel(x, y, w, h, rx, ry, rw, rh)
            info = f"{name}  rank_rel=[{rr[0]:.6f},{rr[1]:.6f},{rr[2]:.6f},{rr[3]:.6f}]  step={step}px"
            cv2.putText(vis, info, (max(8, x+3), max(20, y-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

            # patch du rang (RGB->BGR) + zoom
            patch = table[ry:ry+rh, rx:rx+rw].copy()
            patch_bgr = cv2.cvtColor(patch, cv2.COLOR_RGB2BGR)

            cv2.imshow("table", vis)
            cv2.imshow("rank_patch", patch_bgr)
            show_zoom(patch_bgr, "rank_patch_zoom", factor=3)

            k = cv2.waitKeyEx(0) & 0xFFFFFFFF

            if k == 27:  # ESC -> quitter complètement
                cv2.destroyAllWindows()
                return

            elif k == ord('n'):  # carte suivante
                # on garde l’ajustement en mémoire pour cette session
                node["rank_rel"] = abs_to_rel(x, y, w, h, rx, ry, rw, rh)
                cfg["rois_hint"][name] = node
                i += 1
                break

            elif k in (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN):
                if k == KEY_LEFT:  rx -= step
                if k == KEY_RIGHT: rx += step
                if k == KEY_UP:    ry -= step
                if k == KEY_DOWN:  ry += step
                rx, ry, rw, rh = clamp_rank(x, y, w, h, rx, ry, rw, rh)

            elif k == ord('['):   # largeur --
                rw -= step; rx, ry, rw, rh = clamp_rank(x, y, w, h, rx, ry, max(1, rw), rh)
            elif k == ord(']'):   # largeur ++
                rw += step; rx, ry, rw, rh = clamp_rank(x, y, w, h, rx, ry, rw, rh)
            elif k in (ord('-'), ord('_')):  # hauteur --
                rh -= step; rx, ry, rw, rh = clamp_rank(x, y, w, h, rx, ry, rw, max(1, rh))
            elif k in (ord('+'), ord('=')):  # hauteur ++
                rh += step; rx, ry, rw, rh = clamp_rank(x, y, w, h, rx, ry, rw, rh)

            elif k == ord(','):   # pas --
                step = max(1, step - 1)
            elif k == ord('.'):   # pas ++
                step = min(20, step + 1)

            elif k == ord('g'):   # toggle ombrage
                shade_on = not shade_on

            elif k == ord('p'):   # imprimer rank_rel exact
                rr = abs_to_rel(x, y, w, h, rx, ry, rw, rh)
                print(f"{name}  rank_rel: [{rr[0]:.6f}, {rr[1]:.6f}, {rr[2]:.6f}, {rr[3]:.6f}]")

            elif 32 <= (k & 0xFF) <= 126:  # lettres A,K,Q,...
                ch = chr(k & 0xFF).upper()
                if ch in "AKQJT98765432":
                    idx = len(list(OUT_DIR.glob(f"{ch}_*.png"))) + 1
                    out = OUT_DIR / f"{ch}_{idx:02d}.png"
                    cv2.imwrite(str(out), patch_bgr)
                    print("💾 saved", out)
            elif k == ord('h'):
                print(HELP)

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
