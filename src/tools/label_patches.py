import cv2, shutil
from pathlib import Path

R_UNLAB = Path("assets/dataset/unlabeled/rank")
S_UNLAB = Path("assets/dataset/unlabeled/suit")
R_LAB   = Path("assets/dataset/rank"); S_LAB = Path("assets/dataset/suit")
for d in [R_LAB, S_LAB]: d.mkdir(parents=True, exist_ok=True)

R_KEYS = {ord('a'):"A",ord('k'):"K",ord('q'):"Q",ord('j'):"J",ord('t'):"T",
          ord('2'):"2",ord('3'):"3",ord('4'):"4",ord('5'):"5",ord('6'):"6",
          ord('7'):"7",ord('8'):"8",ord('9'):"9"}
S_KEYS = {ord('h'):"h",ord('d'):"d",ord('s'):"s",ord('c'):"c"}

def label_folder(src_dir, keymap, out_dir, win):
    imgs = sorted(list(src_dir.glob("*.png")))
    for p in imgs:
        img = cv2.imread(str(p))
        cv2.imshow(win, img)
        k = cv2.waitKey(0) & 0xFF
        if k == 27: break
        if k in keymap:
            cls = keymap[k]; (out_dir/cls).mkdir(exist_ok=True, parents=True)
            shutil.move(str(p), str(out_dir/cls/p.name))
        elif k == ord('x'):  # jeter
            p.unlink(missing_ok=True)
    cv2.destroyWindow(win)

if __name__ == "__main__":
    label_folder(R_UNLAB, R_KEYS, R_LAB, "RANK: a/k/q/j/t/2..9; x=trash; ESC=quit")
    label_folder(S_UNLAB, S_KEYS, S_LAB, "SUIT: h/d/s/c; x=trash; ESC=quit")
