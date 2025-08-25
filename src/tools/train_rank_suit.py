import cv2, numpy as np, joblib
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

R_DIR = Path("assets/dataset/rank")
S_DIR = Path("assets/dataset/suit")
MODEL_DIR = Path("models"); MODEL_DIR.mkdir(exist_ok=True)

def preprocess(img_bgr, size=48):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(3.0,(8,8)).apply(gray)
    _, th = cv2.threshold(cv2.GaussianBlur(gray,(3,3),0), 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    if gray.mean()<127: th = 255 - th
    th = cv2.resize(th, (size, size), interpolation=cv2.INTER_AREA)
    x = th.astype(np.float32)/255.0
    return x.reshape(-1)  # flatten

def load_xy(root: Path):
    X, y = [], []
    for cls_dir in sorted(root.glob("*")):
        if not cls_dir.is_dir(): continue
        label = cls_dir.name
        for p in cls_dir.glob("*.png"):
            img = cv2.imread(str(p))
            if img is None: continue
            X.append(preprocess(img))
            y.append(label)
    return np.array(X), np.array(y)

def train_one(root: Path, out_path: Path):
    X, y = load_xy(root)
    if len(np.unique(y)) < 2:
        print(f"❌ Pas assez de classes dans {root}")
        return
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    clf = LogisticRegression(max_iter=2000, n_jobs=-1, multi_class="auto", C=5.0)
    clf.fit(Xtr, ytr)
    yhat = clf.predict(Xte)
    proba = clf.predict_proba(Xte).max(axis=1)
    print(root.name, "acc=", accuracy_score(yte, yhat))
    print(classification_report(yte, yhat))
    joblib.dump(clf, out_path)
    print("✅ Sauvé", out_path)

if __name__ == "__main__":
    train_one(R_DIR, MODEL_DIR/"rank_lr.joblib")
    train_one(S_DIR, MODEL_DIR/"suit_lr.joblib")
