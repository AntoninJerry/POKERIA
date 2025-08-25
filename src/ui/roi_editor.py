from PySide6 import QtWidgets, QtCore, QtGui
import cv2
import numpy as np
from typing import Dict
from src.capture.screen import capture_table
from src.config.settings import get_table_roi, load_room_config, save_room_config, ACTIVE_ROOM
from src.utils.geometry import Rect, clamp_to_bounds, abs_to_rel

HELP = (
    "Éditeur de ROIs — J1\n"
    "Clic-gauche: dessiner | Relâcher: nommer la zone | S: sauvegarder | L: recharger YAML | "
    "Suppr: supprimer la zone sous la souris | Esc: quitter"
)

class RoiEditor(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("POKERIA - Éditeur de ROIs")
        self.setMouseTracking(True)

        # 1) Charger le crop de la TABLE uniquement
        self.table_rect = get_table_roi(ACTIVE_ROOM)
        table_img = capture_table(self.table_rect)  # RGB
        
        # garder une référence et forcer C-contiguous
        self.img = np.ascontiguousarray(table_img, dtype=np.uint8)
        self.H, self.W = self.img.shape[:2]
        self.H, self.W = table_img.shape[:2]
        # utiliser le stride (bytesPerLine)
        self.qimg = QtGui.QImage(
            self.img.data, self.W, self.H, self.img.strides[0],
            QtGui.QImage.Format.Format_RGB888
        )
        self.pix = QtGui.QPixmap.fromImage(self.qimg)

        # 2) Charger ROIs existantes
        self.cfg = load_room_config(ACTIVE_ROOM)
        self.zones: Dict[str, Rect] = {}
        for name, val in self.cfg.get("rois_hint", {}).items():
            rel = val.get("rel", [0,0,0,0])
            # rel -> abs dans espace TABLE (0,0,W,H)
            x = int(rel[0]*self.W); y = int(rel[1]*self.H)
            w = int(rel[2]*self.W); h = int(rel[3]*self.H)
            self.zones[name] = Rect(x,y,max(1,w),max(1,h))

        self.dragging = False
        self.drag_start = QtCore.QPoint()
        self.current_rect = None

        self.resize(self.W, self.H)

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.drawPixmap(0, 0, self.pix)
        # overlay zones
        pen = QtGui.QPen(QtGui.QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen)
        font = p.font(); font.setPointSize(10); p.setFont(font)
        for name, r in self.zones.items():
            p.drawRect(r.x, r.y, r.w, r.h)
            p.drawText(r.x+4, r.y+14, name)

        # en cours de dessin
        if self.dragging and self.current_rect:
            pen = QtGui.QPen(QtGui.QColor("#00E676")); pen.setWidth(2)
            p.setPen(pen)
            r = self.current_rect
            p.drawRect(r.x, r.y, r.w, r.h)

        # aide
        p.setPen(QtGui.QColor("#FFFFFF"))
        font = p.font(); font.setPointSize(12); p.setFont(font)
        p.fillRect(0,0, self.width(), 28, QtGui.QColor(0,0,0,160))
        p.drawText(10, 20, HELP)
        p.end()

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start = ev.position().toPoint()
            self.current_rect = Rect(self.drag_start.x(), self.drag_start.y(), 1, 1)
            self.update()

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        if self.dragging and self.current_rect:
            x0, y0 = self.drag_start.x(), self.drag_start.y()
            x1, y1 = ev.position().toPoint().x(), ev.position().toPoint().y()
            x = min(x0, x1); y = min(y0, y1)
            w = max(1, abs(x1 - x0)); h = max(1, abs(y1 - y0))
            r = Rect(x, y, w, h)
            self.current_rect = clamp_to_bounds(r, Rect(0,0,self.W,self.H))
            self.update()

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == QtCore.Qt.MouseButton.LeftButton and self.current_rect:
            self.dragging = False
            # demander un nom
            name, ok = QtWidgets.QInputDialog.getText(self, "Nom de la zone", "Ex: hero_card_left")
            if ok and name.strip():
                self.zones[name.strip()] = self.current_rect
            self.current_rect = None
            self.update()

    def keyPressEvent(self, ev: QtGui.QKeyEvent):
        k = ev.key()
        if k == QtCore.Qt.Key.Key_S:
            self.save_yaml()
            QtWidgets.QMessageBox.information(self, "Sauvegardé", f"{len(self.zones)} zones écrites dans YAML.")
        elif k == QtCore.Qt.Key.Key_L:
            self.__init__()  # reload
        elif k == QtCore.Qt.Key.Key_Delete:
            self.delete_zone_under_cursor()
        elif k == QtCore.Qt.Key.Key_Escape:
            self.close()

    def delete_zone_under_cursor(self):
        pos = self.mapFromGlobal(QtGui.QCursor.pos())
        px, py = pos.x(), pos.y()
        for name, r in list(self.zones.items()):
            if r.x <= px <= r.x+r.w and r.y <= py <= r.y+r.h:
                del self.zones[name]
                self.update()
                break

    def save_yaml(self):
        # sauver en relatif par rapport à la TABLE (0,0,W,H)
        parent = Rect(0,0,self.W,self.H)
        out = {}
        for name, r in self.zones.items():
            rel = abs_to_rel(parent, r)
            out[name] = {"rel": [round(rel.rx,6), round(rel.ry,6),
                                 round(rel.rw,6), round(rel.rh,6)]}
        self.cfg["rois_hint"] = out
        save_room_config(self.cfg, ACTIVE_ROOM)

def run():
    app = QtWidgets.QApplication([])
    w = RoiEditor()
    w.show()
    app.exec()

if __name__ == "__main__":
    run()
