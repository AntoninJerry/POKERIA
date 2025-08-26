# src/tools/edit_suit_rel.py
import cv2, yaml
from pathlib import Path
from typing import Dict, Tuple
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM

NAMES = [
    "hero_card_left","hero_card_right",
    "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"
]

def rel_to_abs(rel, W, H): rx,ry,rw,rh = rel; return int(rx*W), int(ry*H), int(rw*W), int(rh*H)
def clamp(x,a,b): return max(a, min(b, x))

def _ensure_room_yaml(cfg: Dict) -> Path:
    room_dir = Path("assets/rooms"); room_dir.mkdir(parents=True, exist_ok=True)
    p = Path(cfg.get("_path","")) if cfg.get("_path") else None
    if p and p.exists(): return p
    candidate = room_dir / f"{ACTIVE_ROOM}.yaml"
    if candidate.exists(): return candidate
    files = list(room_dir.glob("*.yaml"))
    if files: return files[0]
    with candidate.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
    print(f"[+] Créé {candidate} (nouveau profil room).")
    return candidate

class Drag:
    def __init__(self):
        self.start_pt = None
        self.end_pt = None
        self.rect = None  # (x,y,w,h) relatif à l'image affichée

    def begin(self, x, y):
        self.start_pt = (x, y)
        self.end_pt = (x, y)
        self._update_rect()

    def update(self, x, y):
        self.end_pt = (x, y)
        self._update_rect()

    def finish(self):
        self._update_rect()

    def clear(self):
        self.start_pt = None
        self.end_pt = None
        self.rect = None

    def _update_rect(self):
        if self.start_pt and self.end_pt:
            x1, y1 = self.start_pt
            x2, y2 = self.end_pt
            x, y = min(x1, x2), min(y1, y2)
            w, h = abs(x2 - x1), abs(y2 - y1)
            self.rect = (x, y, w, h) if w > 0 and h > 0 else None

HELP = "s=save  n=next  p=prev  r=remove  SPACE=refresh  ESC=quit"
TITLE = "EDIT SUIT REL (dessine un rectangle autour du SYMBOLE de la carte)"

def main():
    print("=== EDIT SUIT REL (temps réel) ===")
    print("Instructions: clique-glisse dans la fenêtre pour tracer la zone du SYMBOLE.")
    print("Touches:", HELP)

    cfg = load_room_config(ACTIVE_ROOM)
    room_path = _ensure_room_yaml(cfg)

    idx = 0
    need_refresh_from_screen = True
    crop_bgr = None  # image affichée (BGR)
    rel = None       # ROI carte courante (relatif table)
    name = NAMES[idx]
    drag = Drag()

    cv2.namedWindow(TITLE, cv2.WINDOW_AUTOSIZE)

    def load_current_crop():
        nonlocal crop_bgr, rel, name
        table = capture_table(get_table_roi(ACTIVE_ROOM))  # RGB
        H, W = table.shape[:2]
        name = NAMES[idx]
        rel = cfg.get("rois_hint", {}).get(name, {}).get("rel")
        if not rel:
            # Pas de ROI pour cette carte -> on montre juste la table
            crop_rgb = table
        else:
            x, y, w, h = rel_to_abs(rel, W, H)
            crop_rgb = table[y:y+h, x:x+w]
        crop_bgr = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)

    def on_mouse(event, mx, my, _flags, _userdata):
        if crop_bgr is None or rel is None:
            return
        if event == cv2.EVENT_LBUTTONDOWN:
            drag.begin(mx, my)
        elif event == cv2.EVENT_MOUSEMOVE and drag.start_pt is not None:
            drag.update(mx, my)
        elif event == cv2.EVENT_LBUTTONUP and drag.start_pt is not None:
            drag.update(mx, my)
            drag.finish()

    cv2.setMouseCallback(TITLE, on_mouse)

    while True:
        if need_refresh_from_screen:
            load_current_crop()
            need_refresh_from_screen = False

        # Construit l'image d'affichage à chaque frame
        if crop_bgr is None:
            # Sécurité : rien à afficher
            blank = 255 * (0).to_bytes(1, 'big')  # no-op
        else:
            view = crop_bgr.copy()
            Hc, Wc = view.shape[:2]

            # suit_rel existant -> rectangle vert
            srel = cfg.get("rois_hint", {}).get(name, {}).get("suit_rel")
            if srel:
                sx, sy, sw, sh = rel_to_abs(srel, Wc, Hc)
                cv2.rectangle(view, (sx, sy), (sx+sw, sy+sh), (0, 200, 0), 2)
                cv2.putText(view, "suit_rel EXISTANT", (8, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,0), 1, cv2.LINE_AA)

            # rectangle en cours de drag -> jaune (temps réel)
            if drag.rect:
                x, y, w, h = drag.rect
                x = clamp(x, 0, Wc-1); y = clamp(y, 0, Hc-1)
                w = clamp(w, 1, Wc-x); h = clamp(h, 1, Hc-y)
                cv2.rectangle(view, (x, y), (x+w, y+h), (0, 255, 255), 2)

            # titres / aides
            cv2.putText(view, f"{name}  ({idx+1}/{len(NAMES)})", (8, Hc-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)
            cv2.putText(view, HELP, (8, max(30, Hc-40)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)

            cv2.imshow(TITLE, view)

        k = cv2.waitKey(16) & 0xFF  # ~60 FPS pour l'affichage et la souris

        if k == 27:  # ESC
            break
        elif k in (ord(' '),):  # refresh depuis l'écran
            drag.clear()
            need_refresh_from_screen = True
        elif k in (ord('n'), ord('N')):
            drag.clear()
            idx = (idx + 1) % len(NAMES)
            need_refresh_from_screen = True
        elif k in (ord('p'), ord('P')):
            drag.clear()
            idx = (idx - 1) % len(NAMES)
            need_refresh_from_screen = True
        elif k in (ord('r'), ord('R')) and rel is not None:
            cfg["rois_hint"].setdefault(name, {}).pop("suit_rel", None)
            with open(room_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
            print(f"[-] suit_rel supprimé pour {name}")
        elif k in (ord('s'), ord('S')) and (drag.rect is not None) and rel is not None:
            # sauver suit_rel en coordonnées relatives à la CARTE (crop)
            x, y, w, h = drag.rect
            Hc, Wc = crop_bgr.shape[:2]
            x = clamp(x, 0, Wc-1); y = clamp(y, 0, Hc-1)
            w = clamp(w, 1, Wc-x); h = clamp(h, 1, Hc-y)
            srel = [x/float(Wc), y/float(Hc), w/float(Wc), h/float(Hc)]
            cfg["rois_hint"].setdefault(name, {})["suit_rel"] = srel
            with open(room_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
            print(f"[+] suit_rel enregistré pour {name}: {[round(v,4) for v in srel]}")
            drag.clear()
        # sinon: on continue la boucle

    cv2.destroyAllWindows()
    print("Bye.")

if __name__ == "__main__":
    main()
