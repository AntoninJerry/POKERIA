# src/tools/snap_suit_templates.py
import cv2, os
from pathlib import Path
from typing import Tuple, Dict, Optional
from datetime import datetime

from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM

OUT_DIR = Path("assets/templates/suits")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- helpers ROI ----------
def rel_to_abs(rel, W, H) -> Tuple[int,int,int,int]:
    rx, ry, rw, rh = rel
    return int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H))

def roi(cfg: Dict, name: str):
    v = cfg.get("rois_hint", {}).get(name)
    return v["rel"] if v and "rel" in v else None

def suit_rel(cfg: Dict, name: str):
    v = cfg.get("rois_hint", {}).get(name)
    return v.get("suit_rel") if v else None

def _nonempty(img):
    return img is not None and hasattr(img,"size") and img.size>0 and img.shape[0]>0 and img.shape[1]>0

def _is_small_roi(w,h):
    return w<40 or h<40 or (w*h)<=2000

def _roi_from_rel(img_rgb, rel):
    h, w = img_rgb.shape[:2]
    rx, ry, rw, rh = rel
    x, y = int(rx*w), int(ry*h)
    ww, hh = max(1,int(rw*w)), max(1,int(rh*h))
    x = max(0, min(x, w-1)); y = max(0, min(y, h-1))
    ww = max(1, min(ww, w-x)); hh = max(1, min(hh, h-y))
    return img_rgb[y:y+hh, x:x+ww].copy(), (x,y,ww,hh)

# ---------- extraction coin & symbole ----------
def _prep_bin_otsu(img_rgb, target_h=120):
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(3.0,(8,8)).apply(gray)
    g = cv2.GaussianBlur(gray,(3,3),0)
    _, th = cv2.threshold(g,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if gray.mean() < 127: th = 255 - th
    h,w = th.shape[:2]; s = target_h/max(1.0,h)
    return cv2.resize(th,(max(1,int(w*s)), int(target_h)), interpolation=cv2.INTER_CUBIC)

def _corner_from_crop(crop_rgb):
    h,w = crop_rgb.shape[:2]
    return crop_rgb.copy() if _is_small_roi(w,h) else crop_rgb[0:int(0.55*h), 0:int(0.60*w)].copy()

def _suit_patch_auto(corner_rgb):
    """
    Cherche dynamiquement le symbole dans la moitié droite du coin (contour max).
    Fallback: bloc fixe droite-haut.
    """
    h, w = corner_rgb.shape[:2]
    x1, y1, x2, y2 = int(0.40*w), 0, w, int(0.80*h)
    if x2 <= x1 or y2 <= y1:
        return None
    right = corner_rgb[y1:y2, x1:x2].copy()

    th = _prep_bin_otsu(right, target_h=120)
    try:
        contours, _ = cv2.findContours(255 - th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    except Exception:
        contours = []

    if contours:
        c = max(contours, key=cv2.contourArea)
        x, y, ww, hh = cv2.boundingRect(c)
        if ww*hh >= 16:
            ys1 = max(0, y-2); ys2 = min(th.shape[0], y+hh+2)
            xs1 = max(0, x-2); xs2 = min(th.shape[1], x+ww+2)
            return right[ys1:ys2, xs1:xs2].copy()
    # fallback : coin haut-droit
    fx1, fy2 = int(0.45*w), int(0.75*h)
    if fx1 < w and fy2 > 0:
        return corner_rgb[0:fy2, fx1:w].copy()
    return None

# ---------- main ----------
NAMES = [
    "hero_card_left","hero_card_right",
    "board_card_1","board_card_2","board_card_3","board_card_4","board_card_5"
]

HELP = "h=♥  d=♦  s=♠  c=♣    a=prev  d=next  r=reset-drag  SPACE=refresh  ESC=quit"

class Drag:
    def __init__(self):
        self.start=None; self.end=None; self.rect=None  # (x,y,w,h) relatif AU CROP

    def clear(self): self.start=self.end=None; self.rect=None
    def begin(self,x,y): self.start=(x,y); self.end=(x,y); self._update()
    def update(self,x,y): 
        if self.start is None: return
        self.end=(x,y); self._update()
    def finish(self): self._update()
    def _update(self):
        if self.start and self.end:
            x1,y1=self.start; x2,y2=self.end
            x,y=min(x1,x2),min(y1,y2); w,h=abs(x2-x1),abs(y2-y1)
            self.rect=(x,y,w,h) if w>0 and h>0 else None

def _zoom(img, scale=3):
    h,w = img.shape[:2]
    return cv2.resize(img, (w*scale, h*scale), interpolation=cv2.INTER_NEAREST)

def main():
    print("=== SNAP SUIT TEMPLATES (manuel/auto + noms uniques) ===")
    print("Touches:", HELP)
    cfg = load_room_config(ACTIVE_ROOM)

    patches = []    # [(name, crop_rgb, suit_rel_abs_rect|None)]
    idx = 0
    drag = Drag()

    def collect():
        nonlocal patches, idx
        patches = []
        table = capture_table(get_table_roi(ACTIVE_ROOM))  # RGB
        H,W = table.shape[:2]
        for n in NAMES:
            rel = roi(cfg, n)
            if not rel: 
                continue
            x,y,w,h = rel_to_abs(rel, W, H)
            crop = table[y:y+h, x:x+w].copy()
            if not _nonempty(crop): 
                continue
            srel = suit_rel(cfg, n)
            sabs = None
            if srel:
                _, sabs = _roi_from_rel(crop, srel)
            patches.append((n, crop, sabs))
        idx = 0

    collect()

    WIN1 = "SUIT PATCH (sera enregistré)"
    WIN2 = "SOURCE CROP (carte, drag pour cadrer)"
    cv2.namedWindow(WIN1, cv2.WINDOW_AUTOSIZE)
    cv2.namedWindow(WIN2, cv2.WINDOW_AUTOSIZE)

    def mouse_cb(event, mx, my, _flags, _data):
        if event == cv2.EVENT_LBUTTONDOWN:
            drag.begin(mx,my)
        elif event == cv2.EVENT_MOUSEMOVE:
            drag.update(mx,my)
        elif event == cv2.EVENT_LBUTTONUP:
            drag.update(mx,my); drag.finish()
    cv2.setMouseCallback(WIN2, mouse_cb)

    while True:
        if not patches:
            print("Aucune ROI valide. Vérifie ton YAML. SPACE pour réessayer.")
            k = cv2.waitKey(0) & 0xFF
            if k == 27: break
            if k == ord(' '): collect(); continue
            else: continue

        name, crop, sabs = patches[idx]
        view = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)

        # dessine suit_rel (VERT) si présent
        if sabs:
            x,y,w,h = sabs
            cv2.rectangle(view, (x,y), (x+w,y+h), (0,200,0), 2)
            cv2.putText(view, "suit_rel", (x, max(0,y-5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,200,0), 1, cv2.LINE_AA)

        # dessine drag courant (JAUNE)
        if drag.rect:
            x,y,w,h = drag.rect
            Hc, Wc = view.shape[:2]
            x = max(0,min(x,Wc-1)); y = max(0,min(y,Hc-1))
            w = max(1,min(w,Wc-x)); h = max(1,min(h,Hc-y))
            cv2.rectangle(view, (x,y), (x+w,y+h), (0,255,255), 2)
            cv2.putText(view, "manual", (x, y-5 if y>10 else y+h+15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1, cv2.LINE_AA)

        # Patch “à enregistrer” (priorité drag > suit_rel > auto)
        chosen = None
        if drag.rect:
            x,y,w,h = drag.rect
            x = max(0,min(x, view.shape[1]-1)); y = max(0,min(y, view.shape[0]-1))
            w = max(1,min(w, view.shape[1]-x)); h = max(1,min(h, view.shape[0]-y))
            chosen = crop[y:y+h, x:x+w].copy()
        elif sabs:
            x,y,w,h = sabs
            chosen = crop[y:y+h, x:x+w].copy()
        else:
            # auto depuis le coin
            corner = _corner_from_crop(crop)
            chosen = _suit_patch_auto(corner)

        # Affichage fenêtres
        if _nonempty(chosen):
            cv2.imshow(WIN1, _zoom(cv2.cvtColor(chosen, cv2.COLOR_RGB2BGR), 3))
        else:
            blank = (255 * (0)).to_bytes(1,'big')  # no-op; laisser la dernière vue

        cv2.putText(view, f"{name}  ({idx+1}/{len(patches)})", (8, view.shape[0]-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2, cv2.LINE_AA)
        cv2.putText(view, "h/d/s/c pour ENREGISTRER ce patch", (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)
        cv2.putText(view, "a=prev  d=next  r=reset  SPACE=refresh  ESC=quit", (8, 46),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)
        cv2.imshow(WIN2, _zoom(view, 2))

        k = cv2.waitKey(16) & 0xFF

        if k == 27:  # ESC
            break
        elif k in (ord(' '),):
            drag.clear(); collect(); continue
        elif k in (ord('a'), ord('A')):
            drag.clear(); idx = (idx - 1) % len(patches); continue
        elif k in (ord('n'), ord('N')):
            drag.clear(); idx = (idx + 1) % len(patches); continue
        elif k in (ord('r'), ord('R')):
            drag.clear(); continue
        elif k in (ord('h'), ord('H'), ord('d'), ord('D'), ord('s'), ord('S'), ord('c'), ord('C')):
            if not _nonempty(chosen):
                print("⚠️ Aucun patch sélectionné (définis un drag, suit_rel, ou laisse l’auto trouver).")
                continue
            code = chr(k).lower()  # 'h'/'d'/'s'/'c'
            # dossier par suit
            subdir = OUT_DIR / code
            subdir.mkdir(parents=True, exist_ok=True)
            # nom de fichier unique (microsecondes)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            fname = subdir / f"{code}_{ts}_{name}.png"
            cv2.imwrite(str(fname), cv2.cvtColor(chosen, cv2.COLOR_RGB2BGR))
            print(f"✔ saved: {fname}")
            # on passe au suivant
            drag.clear()
            idx = (idx + 1) % len(patches)

    cv2.destroyAllWindows()
    print("Bye.")

if __name__ == "__main__":
    main()
