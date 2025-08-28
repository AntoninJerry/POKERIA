from __future__ import annotations
import numpy as np
import cv2, mss

from src.utils.geometry import Rect, clamp_to_bounds

def capture_fullscreen_rgb() -> np.ndarray:
    """
    Capture RGB du moniteur principal (index 1 pour mss).
    Retour: np.ndarray [H, W, 3] en RGB uint8.
    """
    with mss.mss() as sct:
        mon = sct.monitors[1]  # écran principal
        raw = np.array(sct.grab(mon))  # BGRA
    # BGRA -> BGR -> RGB
    bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb

def _crop(img: np.ndarray, rect: Rect) -> np.ndarray:
    H, W = img.shape[:2]
    bounded = clamp_to_bounds(rect, Rect(0, 0, W, H))
    return img[bounded.y:bounded.y + bounded.h, bounded.x:bounded.x + bounded.w].copy()

def capture_table(rect: Rect) -> np.ndarray:
    """
    Capture la sous-zone `rect` (en coordonnées écran) depuis la capture plein écran.
    """
    img = capture_fullscreen_rgb()
    return _crop(img, rect)
