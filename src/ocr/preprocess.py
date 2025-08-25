import cv2
import numpy as np

def to_gray(img_rgb):
    return cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

def _clahe(gray):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(gray)

def _unsharp(gray, k=5, amount=1.5, thresh=0):
    blur = cv2.GaussianBlur(gray, (k, k), 0)
    sharp = cv2.addWeighted(gray, 1.0 + amount, blur, -amount, 0)
    if thresh > 0:
        low = np.abs(gray.astype(np.int16) - blur.astype(np.int16)) < thresh
        sharp[low] = gray[low]
    return sharp

def _tophat(gray, k=9):
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    return cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)

def _adaptive(gray, block=31, C=5):
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, block, C)
    if gray.mean() < 127:
        th = 255 - th
    return th

def _otsu(gray):
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if gray.mean() < 127:
        th = 255 - th
    return th

def _morph_refine(th, open_k=(1,1), close_k=(2,2)):
    if open_k != (0,0):
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones(open_k, np.uint8))
    if close_k != (0,0):
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones(close_k, np.uint8))
    return th

def _scale_to_height(img, target_h=64):
    h, w = img.shape[:2]
    if h <= 0: return img
    s = target_h / float(h)
    new_w = max(1, int(w * s))
    return cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_CUBIC)

def preprocess_digits_variants(img_rgb):
    """
    Retourne plusieurs versions binaires/agrandies -> on choisit la meilleure à l'OCR.
    """
    gray = to_gray(img_rgb)
    base = _clahe(_unsharp(gray, k=5, amount=1.0))
    cand = []

    # 1) Adaptive + close
    th1 = _morph_refine(_adaptive(base, 31, 5), open_k=(1,1), close_k=(2,2))
    cand.append(_scale_to_height(th1, 64))

    # 2) Otsu + close
    th2 = _morph_refine(_otsu(base), open_k=(1,1), close_k=(2,2))
    cand.append(_scale_to_height(th2, 64))

    # 3) Top-hat -> Adaptive (aide si fond gris)
    bh = _tophat(base, 9)
    th3 = _morph_refine(_adaptive(bh, 31, 3), open_k=(1,1), close_k=(2,2))
    cand.append(_scale_to_height(th3, 64))

    # 4) Variante épaissie (digits fins)
    th4 = cv2.dilate(th1, np.ones((1,1), np.uint8), iterations=1)
    cand.append(_scale_to_height(th4, 64))

    return cand

def to_rgb(img):
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    return img
