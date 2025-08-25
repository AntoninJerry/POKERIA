import numpy as np
from typing import List, Tuple, Dict
from math import atan2, degrees

def _rel_to_abs(rel, W, H):
    rx, ry, rw, rh = rel
    x = int(rx * W); y = int(ry * H)
    w = max(1, int(rw * W)); h = max(1, int(rh * H))
    return x, y, w, h

def _roi_center(name: str, rois: Dict, W: int, H: int):
    v = rois.get(name)
    if not v or "rel" not in v: 
        return None
    x, y, w, h = _rel_to_abs(v["rel"], W, H)
    return (x + w // 2, y + h // 2)

def _board_centroid(rois: Dict, W: int, H: int):
    pts = []
    for k in range(1, 6):
        c = _roi_center(f"board_card_{k}", rois, W, H)
        if c: pts.append(c)
    if not pts:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))

def seat_centers_from_yaml(W: int, H: int, cfg: Dict) -> List[Tuple[int, int]]:
    rois = cfg.get("rois_hint", {})
    meta = cfg.get("table_meta", {})
    seats_n = int(meta.get("seats_n", 6))

    # 1) centre de table : table_center > barycentre board > centre image
    c = _roi_center("table_center", rois, W, H)
    if c is None:
        c = _board_centroid(rois, W, H)
    if c is None:
        c = (W // 2, H // 2)
    cx, cy = c

    # 2) centre héros : hero_stack > midpoint(hero_card_left/right) > fallback
    h = _roi_center("hero_stack", rois, W, H)
    if h is None:
        hl = _roi_center("hero_card_left", rois, W, H)
        hr = _roi_center("hero_card_right", rois, W, H)
        if hl and hr:
            h = ((hl[0] + hr[0]) // 2, (hl[1] + hr[1]) // 2)
    if h is None:
        h = (cx, int(H * 0.85))  # fallback sous le centre
    hx, hy = h

    # 3) rayon : distance centre->héros (cercle)
    r = max(int(np.hypot(hx - cx, hy - cy)), int(min(W, H) * 0.28))
    rx = r
    ry = r  # cercle. Si tu veux ellipse, mets par ex. ry = int(r * 0.92)

    # 4) angle de base : héros = index 0
    base_deg = degrees(atan2(hy - cy, hx - cx))  # [-180..180]

    pts = []
    step = 360.0 / float(seats_n)
    for k in range(seats_n):
        a = np.deg2rad(base_deg + k * step)  # CW/CCW n'a pas d'importance pour le mapping bouton
        x = int(cx + rx * np.cos(a))
        y = int(cy + ry * np.sin(a))
        pts.append((x, y))
    return pts

def nearest_seat(x: int, y: int, centers: List[Tuple[int, int]]) -> int:
    dists = [(i, (cx - x) ** 2 + (cy - y) ** 2) for i, (cx, cy) in enumerate(centers)]
    return min(dists, key=lambda t: t[1])[0]

def seat_centers(w: int, h: int, seats_n: int = 6, hero_bottom: bool = True) -> List[Tuple[int, int]]:
    cx, cy = w // 2, int(h * 0.53)       # centre légèrement abaissé
    rx, ry = int(w * 0.42), int(h * 0.38)  # rayons ellipse (à ajuster si besoin)
    base_angle = -90 if hero_bottom else 0 # siège 0 en bas
    angles = np.linspace(0, 360, seats_n, endpoint=False) + base_angle
    pts = []
    for a in angles:
        rad = np.deg2rad(a)
        x = int(cx + rx * np.cos(rad))
        y = int(cy + ry * np.sin(rad))
        pts.append((x, y))
    return pts