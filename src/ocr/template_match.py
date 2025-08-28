# src/ocr/template_match.py
import os, cv2, glob
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional

def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.shape[2] == 3 else cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

def _binarize(gray: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gray, (3,3), 0)
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 5)
    if gray.mean() < 127:  # uniformise “police claire”
        th = 255 - th
    return th

def load_templates_from_dir(root: str, labels: Optional[List[str]] = None) -> Dict[str, List[np.ndarray]]:
    """
    Charge des templates par label. Structure attendue:
    assets/templates/ranks/
      A_*.png, K_*.png, Q_*.png, ... 2_*.png
    Retour: { 'A': [img,...], 'K': [...], ... }
    """
    rootp = Path(root)
    out: Dict[str, List[np.ndarray]] = {}
    if not rootp.exists():
        return out
    pats = sorted(glob.glob(str(rootp / "*.png")))
    for p in pats:
        stem = Path(p).stem  # ex: Q_01
        lab = stem.split("_")[0].upper()
        if labels and lab not in labels:
            continue
        img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if img is None: 
            continue
        out.setdefault(lab, []).append(img)
    return out

def best_match_rank(patch_rgb: np.ndarray,
                    bank: Dict[str, List[np.ndarray]],
                    scales: Tuple[float, ...] = (0.7, 0.85, 1.0)) -> Tuple[Optional[str], float]:
    """
    Matche un caractère (RANK) dans un patch. On redimensionne les templates
    à ~70–100% de la hauteur du patch, puis cv2.TM_CCOEFF_NORMED.
    Retour: (label, score) avec score ∈ [0,1].
    """
    if patch_rgb is None or patch_rgb.size == 0:
        return None, 0.0

    gray = _to_gray(patch_rgb)
    th = _binarize(gray)
    H, W = th.shape[:2]
    best_lab, best_score = None, -1.0

    for lab, imgs in bank.items():
        for tpl in imgs:
            if tpl is None or tpl.size == 0: 
                continue
            for s in scales:
                th_h = max(6, int(H * s))
                s_ratio = th_h / max(1, tpl.shape[0])
                tpl_s = cv2.resize(tpl, (max(3, int(tpl.shape[1]*s_ratio)), th_h),
                                   interpolation=cv2.INTER_AREA)
                if tpl_s.shape[0] > th.shape[0] or tpl_s.shape[1] > th.shape[1]:
                    continue
                res = cv2.matchTemplate(th, tpl_s, cv2.TM_CCOEFF_NORMED)
                score = float(res.max()) if res.size else -1.0
                if score > best_score:
                    best_score, best_lab = score, lab

                # Essai inversé (par sécurité)
                res_inv = cv2.matchTemplate(255 - th, tpl_s, cv2.TM_CCOEFF_NORMED)
                score_inv = float(res_inv.max()) if res_inv.size else -1.0
                if score_inv > best_score:
                    best_score, best_lab = score_inv, lab

    return best_lab, max(0.0, best_score)

# --- suits ---
def load_suit_templates_from_dir(root: str) -> dict:
    # h_*.png, d_*.png, s_*.png, c_*.png
    import glob, cv2, numpy as np
    from pathlib import Path
    out={}
    for lab in ("h","d","s","c"):
        files=sorted(glob.glob(str(Path(root)/f"{lab}_*.png")))
        arr=[]
        for p in files:
            img=cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is not None: arr.append(img)
        out[lab]=arr
    return out

def best_match_suit(patch_rgb, bank: dict, scales=(0.6, 0.8, 1.0)):
    import cv2, numpy as np
    if patch_rgb is None or getattr(patch_rgb, "size", 0) == 0:
        return None, 0.0

    # Gray + bin
    if patch_rgb.ndim == 3:
        gray = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2GRAY)
    else:
        gray = patch_rgb.copy()
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 5)
    if gray.mean() < 127:
        th = 255 - th

    H, W = th.shape[:2]
    best_score = -1.0
    best_lab = None

    for lab, imgs in bank.items():
        if not imgs:
            continue
        for tpl in imgs:
            if tpl is None or getattr(tpl, "size", 0) == 0:
                continue
            for s in scales:
                th_h = max(6, int(H * s))
                s_ratio = th_h / max(1, tpl.shape[0])
                tpl_s = cv2.resize(
                    tpl,
                    (max(3, int(tpl.shape[1] * s_ratio)), th_h),
                    interpolation=cv2.INTER_AREA
                )
                if tpl_s.shape[0] > H or tpl_s.shape[1] > W:
                    continue

                # normal
                res = cv2.matchTemplate(th, tpl_s, cv2.TM_CCOEFF_NORMED)
                score = float(res.max()) if res.size else -1.0
                if score > best_score:
                    best_score = score
                    best_lab = lab

                # inversé (sécurité)
                res2 = cv2.matchTemplate(255 - th, tpl_s, cv2.TM_CCOEFF_NORMED)
                score2 = float(res2.max()) if res2.size else -1.0
                if score2 > best_score:
                    best_score = score2
                    best_lab = lab

    return best_lab, max(0.0, best_score)

