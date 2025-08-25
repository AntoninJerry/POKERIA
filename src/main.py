from pathlib import Path
import sys

# assure le chemin racine pour imports "src.*"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.ui.calibrator import run_calibrator

if __name__ == "__main__":
    run_calibrator()
