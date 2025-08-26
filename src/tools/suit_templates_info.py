# src/tools/suit_templates_info.py
from src.ocr.suit_shape import SuitHu

def main():
    clf = SuitHu()
    print("TEMPL_DIR :", clf.templates_dir())
    print("COUNTS    :", clf.template_counts())
    if sum(clf.template_counts().values()) == 0:
        print("⚠️ Aucun template chargé. Vérifie le chemin et l'extension .png")
    else:
        print("✅ Templates OK.")

if __name__ == "__main__":
    main()
