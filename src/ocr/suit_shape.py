import cv2, numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional

TEMPL_DIR = Path("assets/templates/suits")  # mets 1–3 petits crops par suit: heart*.png, diamond*.png, spade*.png, club*.png

def _nonempty(img):
    return img is not None and hasattr(img, "size") and img.size > 0 and img.shape[0] > 0 and img.shape[1] > 0

def _prep_bin(bgr, target=64):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.createCLAHE(3.0,(8,8)).apply(g)
    g = cv2.GaussianBlur(g,(3,3),0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if g.mean() < 127: th = 255 - th
    th = cv2.resize(th, (target, target), interpolation=cv2.INTER_AREA)
    return th

def _hu(th):
    m = cv2.moments(th)
    hu = cv2.HuMoments(m).flatten()
    # log transform (stabilité)
    hu = -np.sign(hu) * np.log10(np.abs(hu) + 1e-12)
    return hu

def _dist(a, b):
    return float(np.linalg.norm(a - b))

def _edge_bgr(img_bgr):
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g,(3,3),0)
    return cv2.Canny(g, 80, 160)

def _tm_score(bgr, templs):
    if not templs: return -1.0
    edge = _edge_bgr(bgr)
    best = -1.0
    for t in templs:
        te = _edge_bgr(t)
        for s in np.linspace(0.7, 1.4, 10):
            tw, th = int(t.shape[1]*s), int(t.shape[0]*s)
            if tw<5 or th<5 or tw>bgr.shape[1] or th>bgr.shape[0]: continue
            t_res  = cv2.resize(t,  (tw, th))
            te_res = cv2.resize(te, (tw, th))
            r1 = cv2.matchTemplate(bgr,  t_res,  cv2.TM_CCOEFF_NORMED).max()
            r2 = cv2.matchTemplate(edge, te_res, cv2.TM_CCOEFF_NORMED).max()
            best = max(best, 0.4*float(r1) + 0.6*float(r2))
    return best

class SuitHu:
    def __init__(self):
        self.db: Dict[str, List[np.ndarray]] = {"h":[], "d":[], "s":[], "c":[]}
        self._load()

    def _load(self):
        if not TEMPL_DIR.exists(): return
        for code, keys in [("h", ["heart", "h_"]), ("d", ["diamond", "d_"]),
                           ("s", ["spade", "s_"]), ("c", ["club", "c_"])]:
            for k in keys:
                for p in sorted(TEMPL_DIR.glob(f"{k}*.png")):
                    img = cv2.imread(str(p))
                    if img is None: continue
                    th = _prep_bin(img)
                    self.db[code].append(_hu(th))

    def classify(self, suit_patch_rgb, color_hint: Optional[str]):
        if not _nonempty(suit_patch_rgb):
        # fallback direct à la couleur si le patch est vide
            return ("h" if color_hint == "red" else "s"), 0.5, {"reason": "empty_patch"}
        bgr = cv2.cvtColor(suit_patch_rgb, cv2.COLOR_RGB2BGR)
        if not any(self.db.values()):
            return None, 0.0, {"reason":"no_templates"}
        bgr = cv2.cvtColor(suit_patch_rgb, cv2.COLOR_RGB2BGR)
        th  = _prep_bin(bgr)
        f   = _hu(th)

        # candidats restreints par couleur
        cand = ["h","d"] if color_hint=="red" else ["s","c"] if color_hint=="black" else ["h","d","s","c"]
        scores = []
        for c in cand:
            if not self.db[c]: continue
            dmin = min(_dist(f, t) for t in self.db[c])
            hu_conf = 1.0 / (1.0 + dmin)           # [0..1], plus grand = mieux
            tm_conf = max(0.0, _tm_score(bgr, [cv2.imread(str(p)) for p in []]))  # placeholder si tu veux passer des tm dédiés
            # si tu n'as pas de tm dédiés par suit, garde hu_conf seul :
            final = 0.6*hu_conf + 0.4*tm_conf if tm_conf > 0 else hu_conf
            scores.append((c, final, hu_conf, tm_conf, dmin))

        if not scores:
            return None, 0.0, {"reason":"no_candidates"}

        scores.sort(key=lambda x: x[1], reverse=True)
        best, second = scores[0], scores[1] if len(scores)>1 else (scores[0][0], 0.0, 0.0, 0.0, 0.0)
        margin = float(best[1] - (second[1] if isinstance(second, tuple) else second))

        # marge un peu plus stricte pour séparer ♥/♦ et ♠/♣
        if margin >= 0.08:
            return best[0], float(best[1]), {"margin":margin, "hu":best[2], "tm":best[3]}
        # doute -> fallback à la couleur
        return ("h" if color_hint=="red" else "s"), 0.5, {"margin":margin, "fallback":"color"}
