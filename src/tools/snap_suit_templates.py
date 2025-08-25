import cv2
from pathlib import Path
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, ACTIVE_ROOM

OUT_DIR = Path("assets/templates/suits")

def main():
    img = capture_table(get_table_roi(ACTIVE_ROOM))
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    clone = bgr.copy()
    drawing = False; p0=(0,0)

    def on_mouse(event, x, y, flags, param):
        nonlocal drawing, p0, bgr
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True; p0=(x,y)
        elif event == cv2.EVENT_MOUSEMOVE and drawing:
            bgr = clone.copy(); cv2.rectangle(bgr, p0, (x,y), (0,255,0), 2)
        elif event == cv2.EVENT_LBUTTONUP:
            drawing = False
            x1,y1 = min(p0[0],x), min(p0[1],y)
            x2,y2 = max(p0[0],x), max(p0[1],y)
            crop = clone[y1:y2, x1:x2].copy()
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            cv2.imshow("crop", crop)
            key = cv2.waitKey(0) & 0xFF
            name = {ord('s'):"spade", ord('c'):"club", ord('h'):"heart", ord('d'):"diamond"}.get(key)
            if name:
                cv2.imwrite(str(OUT_DIR/f"{name}.png"), crop)
                print(f"✅ Saved {name}.png")

    cv2.namedWindow("Draw box over a SUIT, then press s/c/h/d to save template")
    cv2.setMouseCallback("Draw box over a SUIT, then press s/c/h/d to save template", on_mouse)
    while True:
        cv2.imshow("Draw box over a SUIT, then press s/c/h/d to save template", bgr)
        if cv2.waitKey(20) & 0xFF == 27: break
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
