import os, glob
from src.ocr.template_match import load_templates_from_dir

root = os.getenv("POKERIA_RANKS_DIR", "assets/templates/ranks")
print("RANK TPL PATH:", root)

cnt = len(glob.glob(root + "/*.png"))
print("nb_png:", cnt)

bank = load_templates_from_dir(root, list("23456789TJQKA"))
print({k: len(v) for k, v in bank.items()})
