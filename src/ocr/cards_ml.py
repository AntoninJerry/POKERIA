import cv2, numpy as np, joblib
from pathlib import Path

MODEL_DIR = Path("models")
R_PATH = MODEL_DIR/"rank_lr.joblib"
S_PATH = MODEL_DIR/"suit_lr.joblib"

def _prep(bgr, size=48):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(3.0,(8,8)).apply(gray)
    _, th = cv2.threshold(cv2.GaussianBlur(gray,(3,3),0), 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if gray.mean()<127: th = 255 - th
    th = cv2.resize(th, (size, size), interpolation=cv2.INTER_AREA)
    x = th.astype(np.float32)/255.0
    return x.reshape(1,-1)

class RankSuitML:
    def __init__(self):
        self.rank = joblib.load(R_PATH) if R_PATH.exists() else None
        self.suit = joblib.load(S_PATH) if S_PATH.exists() else None

    def predict_rank(self, patch_rgb):
        if self.rank is None: return None, 0.0
        bgr = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2BGR)
        X = _prep(bgr)
        probs = self.rank.predict_proba(X)[0]
        idx = int(np.argmax(probs))
        return self.rank.classes_[idx], float(probs[idx])

    def predict_suit(self, patch_rgb):
        if self.suit is None: return None, 0.0
        bgr = cv2.cvtColor(patch_rgb, cv2.COLOR_RGB2BGR)
        X = _prep(bgr)
        probs = self.suit.predict_proba(X)[0]
        idx = int(np.argmax(probs))
        return self.suit.classes_[idx], float(probs[idx])
