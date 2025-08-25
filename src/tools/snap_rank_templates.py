import cv2
from pathlib import Path
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, ACTIVE_ROOM

OUT_DIR = Path("assets/templates/ranks")
KEYMAP = {
    ord('a'): "A", ord('k'): "K", ord('q'): "Q", ord('j'): "J", ord('t'): "T",
    ord('2'): "2", ord('3'): "3", ord('4'): "4", ord('5'): "5",
    ord('6'): "6", ord('7'): "7", ord('8'): "8", ord('9'): "9",
    ord('0'): "T"  # '0' == 10 -> T
}

MIN_W, MIN_H = 8, 12  # taille mini du template pour éviter les crops vides

def main():
    img = capture_table(get_table_roi(ACTIVE_ROOM))   # RGB
    bgr0 = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    bgr = bgr0.copy()
    H, W = bgr.shape[:2]
    clone = bgr.copy()
    drawing = False
    p0 = (0, 0)

    win = "Trace un rectangle SUR LE RANG (coin TL), puis appuie a/k/q/j/t/2..9, 0=10. ESC pour quitter."
    cv2.namedWindow(win)

    def clamp_box(x1, y1, x2, y2):
        x1 = max(0, min(x1, W - 1)); x2 = max(0, min(x2, W - 1))
        y1 = max(0, min(y1, H - 1)); y2 = max(0, min(y2, H - 1))
        if x2 < x1: x1, x2 = x2, x1
        if y2 < y1: y1, y2 = y2, y1
        return x1, y1, x2, y2

    def on_mouse(event, x, y, flags, param):
        nonlocal drawing, p0, bgr
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            p0 = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and drawing:
            bgr = clone.copy()
            x1, y1, x2, y2 = clamp_box(p0[0], p0[1], x, y)
            cv2.rectangle(bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
        elif event == cv2.EVENT_LBUTTONUP and drawing:
            drawing = False
            x1, y1, x2, y2 = clamp_box(p0[0], p0[1], x, y)
            w, h = (x2 - x1), (y2 - y1)
            if w < MIN_W or h < MIN_H:
                print("⚠️  Sélection trop petite — recommence (au moins 8×12).")
                return
            crop = clone[y1:y2, x1:x2].copy()
            if crop.size == 0:
                print("⚠️  Crop vide (hors image). Recommence.")
                return
            cv2.imshow("RANK CROP (appuie sur la touche du rang)", crop)
            key = cv2.waitKey(0) & 0xFF
            if key in KEYMAP:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                code = KEYMAP[key]
                out = OUT_DIR / f"{code}_{x1}_{y1}.png"
                cv2.imwrite(str(out), crop)
                print(f"✅ Rank template sauvegardé: {out}")
            cv2.destroyWindow("RANK CROP (appuie sur la touche du rang)")

    cv2.setMouseCallback(win, on_mouse)

    while True:
        cv2.imshow(win, bgr)
        k = cv2.waitKey(20) & 0xFF
        if k == 27:  # ESC
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
