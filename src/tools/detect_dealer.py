import cv2, numpy as np
from pathlib import Path
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.state.seating import seat_centers, nearest_seat, seat_centers_from_yaml

TEMPLATE_PATH = Path("assets/templates/dealer_button.png")

def match_template(img_bgr, templ_bgr):
    tH, tW = templ_bgr.shape[:2]
    best = (None, -1, (0,0), 1.0)
    for s in np.linspace(0.6, 1.4, 11):
        resized = cv2.resize(templ_bgr, (int(tW*s), int(tH*s)))
        if resized.shape[0] >= img_bgr.shape[0] or resized.shape[1] >= img_bgr.shape[1]:
            continue
        res = cv2.matchTemplate(img_bgr, resized, cv2.TM_CCOEFF_NORMED)
        _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
        if maxVal > best[1]:
            best = (res, maxVal, maxLoc, s)
    return best  # (res, score, topLeft, scale)

def detect_by_template(img_bgr):
    if not TEMPLATE_PATH.exists():
        return None
    templ = cv2.imread(str(TEMPLATE_PATH))
    _, score, topLeft, s = match_template(img_bgr, templ)
    if score < 0.55:
        return None
    h, w = int(templ.shape[0]*s), int(templ.shape[1]*s)
    center = (int(topLeft[0] + w/2), int(topLeft[1] + h/2))
    return center, score

def detect_by_hough(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    H, W = gray.shape
    minR = int(min(W, H) * 0.015)
    maxR = int(min(W, H) * 0.05)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=40,
                               param1=120, param2=30, minRadius=minR, maxRadius=maxR)
    if circles is None:
        return None
    circles = np.round(circles[0, :]).astype("int")
    # on prend le cercle avec le plus d'edges (proxy de "marqué")
    best = None
    for (x, y, r) in circles:
        y1, y2 = max(0, y-r), min(H, y+r)
        x1, x2 = max(0, x-r), min(W, x+r)
        patch = gray[y1:y2, x1:x2]
        edges = cv2.Canny(patch, 50, 150)
        score = float(edges.mean())
        if best is None or score > best[2]:
            best = (x, y, score)
    if best:
        return (best[0], best[1]), best[2]/255.0
    return None

def main():
    table_rgb = capture_table(get_table_roi(ACTIVE_ROOM))
    img_bgr = cv2.cvtColor(table_rgb, cv2.COLOR_RGB2BGR)
    H, W = img_bgr.shape[:2]

    # 1) template si dispo, sinon 2) Hough
    res = detect_by_template(img_bgr)
    if res is None:
        res = detect_by_hough(img_bgr)
    if res is None:
        print("❌ Dealer non détecté.")
        return
    (cx, cy), score = res
    print(f"✅ Dealer détecté à ({cx},{cy}) score={score:.2f}")

    cfg = load_room_config(ACTIVE_ROOM)
    rois_hint = cfg.get("rois_hint", {})
    seats_n = cfg.get("table_meta", {}).get("seats_n", 6)

    centers = seat_centers_from_yaml(W, H, cfg)  # <-- nouveau calcul data-driven
    seat_idx = nearest_seat(cx, cy, centers)
    print(f"Seat bouton estimé: s{seat_idx+1}/{seats_n}")

    # Visualisation
    vis = img_bgr.copy()
    for i, (sx, sy) in enumerate(centers):
        cv2.circle(vis, (sx, sy), 6, (0,255,0), -1)
        cv2.putText(vis, f"s{i+1}", (sx+8, sy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
    cv2.circle(vis, (cx, cy), 10, (0,0,255), 2)
    cv2.imshow("Dealer detection", vis)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
