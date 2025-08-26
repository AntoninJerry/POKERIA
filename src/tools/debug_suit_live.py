# src/tools/debug_suit_live.py
import cv2
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, ACTIVE_ROOM
from src.ocr.suit_shape import SuitHu
from src.ocr.cards import _prep_bin_otsu, _refine_by_biggest_contour, _nonempty

NAMES = ["board_card_1","board_card_2","board_card_3","board_card_4","board_card_5",
         "hero_card_left","hero_card_right"]

def rel_to_abs(rel, W, H):
    rx,ry,rw,rh = rel; return int(rx*W), int(ry*H), max(1,int(rw*W)), max(1,int(rh*H))

def main():
    cfg = load_room_config(ACTIVE_ROOM)
    clf = SuitHu()
    print("TEMPL_DIR:", clf.templates_dir(), "COUNTS:", clf.template_counts())

    idx = 0
    while True:
        table = capture_table(get_table_roi(ACTIVE_ROOM))
        H,W = table.shape[:2]
        n = NAMES[idx]
        rel = (cfg.get("rois_hint",{}).get(n,{}) or {}).get("rel")
        srel = (cfg.get("rois_hint",{}).get(n,{}) or {}).get("suit_rel")
        if not rel:
            print(f"{n}: pas de rel"); idx=(idx+1)%len(NAMES); continue
        x,y,w,h = rel_to_abs(rel,W,H)
        crop = table[y:y+h, x:x+w].copy()
        patch = None
        if srel:
            rx,ry,rw,rh = srel
            xs,ys,ws,hs = int(rx*w), int(ry*h), int(rw*w), int(rh*h)
            patch = crop[ys:ys+hs, xs:xs+ws].copy()

        if not _nonempty(patch):  # si pas de suit_rel, tente auto sur coin TL
            corner = crop[0:int(0.55*h), 0:int(0.60*w)].copy()
            patch = corner

        patch = _refine_by_biggest_contour(patch, pad=2)

        if _nonempty(patch):
            code, conf, meta = clf.classify(patch, color_hint=None)
            th = _prep_bin_otsu(patch, 120)
            vis = cv2.cvtColor(patch, cv2.COLOR_RGB2BGR)
            cv2.putText(vis, f"{n} -> {code} conf={conf:.2f}", (5,18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 1, cv2.LINE_AA)
            cv2.imshow("SUIT PATCH", cv2.resize(vis, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST))
            cv2.imshow("BINARY", cv2.resize(th, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST))
        else:
            print(f"{n}: patch vide")

        k = cv2.waitKey(0) & 0xFF
        if k == 27: break
        if k in (ord('a'),): idx = (idx-1) % len(NAMES)
        if k in (ord('d'),): idx = (idx+1) % len(NAMES)

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
