import numpy as np
import cv2
import mss
from src.utils.geometry import Rect, clamp_to_bounds

def capture_fullscreen_rgb() -> np.ndarray:
    with mss.mss() as sct:
        mon = sct.monitors[1]  # écran principal
        raw = np.array(sct.grab(mon))  # BGRA
    bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb  # HxWx3

def crop(img, r):
    H, W = img.shape[:2]
    bounded = clamp_to_bounds(r, Rect(0, 0, W, H))
    return img[bounded.y:bounded.y+bounded.h, bounded.x:bounded.x+bounded.w].copy()

def capture_table(rect: Rect) -> np.ndarray:
    img = capture_fullscreen_rgb()
    return crop(img, rect)
