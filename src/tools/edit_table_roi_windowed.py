# src/tools/edit_table_roi_windowed.py
import cv2
from pathlib import Path
from typing import Optional, Tuple

from src.capture.screen import capture_fullscreen_rgb
from src.config.settings import (
    load_room_config,
    save_room_config,
    room_yaml_path,
    ACTIVE_ROOM,
)

HELP = (
    "=== EDIT TABLE ROI (WINDOWED) ===\n"
    "1) Une capture plein écran s'affiche\n"
    "2) Sélectionne la TABLE avec la souris (cv2.selectROI)\n"
    "3) Appuie sur ENTER pour valider la sélection\n"
    "4) La ROI est sauvée dans le YAML actif (room)\n"
    "ESC pour quitter."
)

def _select_roi(bgr) -> Optional[Tuple[int, int, int, int]]:
    cv2.namedWindow("Select TABLE ROI (WINDOWED)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Select TABLE ROI (WINDOWED)", 1280, 720)
    r = cv2.selectROI("Select TABLE ROI (WINDOWED)", bgr, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("Select TABLE ROI (WINDOWED)")
    x, y, w, h = map(int, r)
    if w <= 1 or h <= 1:
        return None
    return x, y, w, h

def main():
    print(HELP)
    # 1) Screenshot plein écran
    img_rgb = capture_fullscreen_rgb()
    bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    # 2) Sélection de la table fenêtrée
    roi = _select_roi(bgr)
    if roi is None:
        print("❌ Aucune sélection valide. Abandon.")
        return

    x, y, w, h = roi
    # 3) Charger et mettre à jour la config active
    cfg = load_room_config(ACTIVE_ROOM)
    cfg["table_roi"] = {"left": x, "top": y, "width": w, "height": h}

    # 4) Sauvegarder via l’API settings (même chemin que le loader)
    save_room_config(cfg, ACTIVE_ROOM)
    print("✅ ROI table sauvegardée.")
    print("   Fichier :", room_yaml_path(ACTIVE_ROOM))

if __name__ == "__main__":
    main()
