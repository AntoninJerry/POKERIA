# src/ocr/preprocess.py
from __future__ import annotations
import os
import cv2
import numpy as np

# ──────────────────────────
# Optimisations globales OpenCV / BLAS (une fois)
# ──────────────────────────
try:
    cv2.setUseOptimized(True)
    try:
        cv2.setNumThreads(max(1, os.cpu_count()//2))
    except Exception:
        pass
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("MKL_NUM_THREADS", "4")
except Exception:
    pass

# ──────────────────────────
# Conversions de base
# ──────────────────────────
def to_gray(img_rgb: np.ndarray) -> np.ndarray:
    """RGB → GRAY (uint8)."""
    if img_rgb is None:
        return None
    if len(img_rgb.shape) == 2:
        return img_rgb
    return cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

def to_rgb(img: np.ndarray) -> np.ndarray:
    """Assure un RGB 3 canaux (uint8)."""
    if img is None:
        return None
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    return img

# ──────────────────────────
# Filtres de base
# ──────────────────────────
def _clahe(gray: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)

def _unsharp(gray: np.ndarray, k: int = 5, amount: float = 1.25, thresh: int = 0) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (k, k), 0)
    sharp = cv2.addWeighted(gray, 1.0 + amount, blur, -amount, 0)
    if thresh > 0:
        low = np.abs(gray.astype(np.int16) - blur.astype(np.int16)) < thresh
        sharp[low] = gray[low]
    return sharp

def _tophat(gray: np.ndarray, k: int = 9) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    return cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)

def _adaptive(gray: np.ndarray, block: int = 31, C: int = 5) -> np.ndarray:
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, block, C)
    if gray.mean() < 127:
        th = 255 - th
    return th

def _otsu(gray: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if gray.mean() < 127:
        th = 255 - th
    return th

def _morph_refine(th: np.ndarray, open_k=(1, 1), close_k=(2, 2)) -> np.ndarray:
    if open_k != (0, 0):
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones(open_k, np.uint8))
    if close_k != (0, 0):
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones(close_k, np.uint8))
    return th

def _scale_to_height(img: np.ndarray, target_h: int = 64) -> np.ndarray:
    h, w = img.shape[:2]
    if h <= 0:
        return img
    s = target_h / float(h)
    new_w = max(1, int(w * s))
    return cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_CUBIC)

# ──────────────────────────
# Indicateurs de présence / couleur (pour abstention)
# ──────────────────────────
def red_ratio(img_rgb: np.ndarray) -> float:
    b,g,r = cv2.split(img_rgb)
    rr = (r.astype(np.int32) - ((g.astype(np.int32)+b.astype(np.int32))//2))
    rr = np.clip(rr, 0, 255).astype(np.uint8)
    return float((rr > 30).mean())

def card_presence_score(img_rgb: np.ndarray, min_edge_density: float = 0.012, min_white_ratio: float = 0.04) -> tuple[float, bool]:
    """
    Renvoie (score, present_bool).
    Score combine: bordures (Canny), blancs (cadre de carte), aire contour max.
    """
    h, w = img_rgb.shape[:2]
    if h*w == 0:
        return 0.0, False

    gray = to_gray(img_rgb)
    white = (gray > 210).astype(np.uint8)
    white_ratio = float(white.mean())

    edges = cv2.Canny(gray, 55, 110)
    edge_density = float(edges.mean()) / 255.0

    cnts, _ = cv2.findContours((gray > 160).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    max_area = 0.0
    for c in cnts:
        a = cv2.contourArea(c)
        if a > max_area:
            max_area = a
    area_ratio = float(max_area) / (h*w)

    score = 0.5*edge_density + 0.35*white_ratio + 0.15*area_ratio
    ok = (edge_density >= min_edge_density) and (white_ratio >= min_white_ratio)
    return float(score), bool(ok)

# ──────────────────────────
# Pipeline montants (pot / stack)
# ──────────────────────────
def preprocess_digits(img_rgb: np.ndarray) -> np.ndarray:
    """
    Prétraitement principal pour montants (€):
      - gris + CLAHE + léger unsharp
      - Otsu (inversion auto si fond sombre)
      - petite morpho (open/close)
      - upscale (H=64)
    Retour: image binaire (uint8 0/255), 1 canal.
    """
    gray = to_gray(img_rgb)
    gray = _clahe(gray)
    gray = _unsharp(gray, k=5, amount=1.0)

    th = _otsu(gray)
    th = _morph_refine(th, open_k=(1, 1), close_k=(2, 2))
    th = _scale_to_height(th, 64)
    return th

def preprocess_digits_variants(img_rgb: np.ndarray) -> list[np.ndarray]:
    """Génère plusieurs binaires agrandis pour tenter l’OCR et garder la meilleure."""
    gray = to_gray(img_rgb)
    base = _clahe(_unsharp(gray, k=5, amount=1.0))

    cand = []
    # 1) Adaptive + close
    th1 = _morph_refine(_adaptive(base, 31, 5), open_k=(1, 1), close_k=(2, 2))
    cand.append(_scale_to_height(th1, 64))

    # 2) Otsu + close
    th2 = _morph_refine(_otsu(base), open_k=(1, 1), close_k=(2, 2))
    cand.append(_scale_to_height(th2, 64))

    # 3) Top-hat → Adaptive (utile fond gris)
    bh = _tophat(base, 9)
    th3 = _morph_refine(_adaptive(bh, 31, 3), open_k=(1, 1), close_k=(2, 2))
    cand.append(_scale_to_height(th3, 64))

    # 4) Variante légère épaissie (digits fins)
    th4 = cv2.dilate(th1, np.ones((1, 1), np.uint8), iterations=1)
    cand.append(_scale_to_height(th4, 64))

    return cand