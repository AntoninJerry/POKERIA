from PySide6 import QtWidgets, QtCore, QtGui
import numpy as np
import cv2
from src.capture.screen import capture_fullscreen_rgb, crop
from src.config.settings import get_table_roi, set_table_roi, ACTIVE_ROOM
from src.utils.geometry import Rect

INSTR = (
    "Calibrateur ROI — J1\n"
    "Souris: cliquez-glissez pour dessiner la ROI ; glissez à l'intérieur pour déplacer.\n"
    "Flèches: ajuster au pixel   |   R: reset   |   V: preview   |   S: sauvegarder   |   Esc: quitter"
)

class Calibrator(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("POKERIA - Calibrateur ROI")
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, False)
        self.setMouseTracking(True)

        self.img = capture_fullscreen_rgb()              # numpy RGB
        self.H, self.W = self.img.shape[:2]
        self.qimg = QtGui.QImage(self.img.data, self.W, self.H, self.W*3,
                                 QtGui.QImage.Format.Format_RGB888)
        self.pix = QtGui.QPixmap.fromImage(self.qimg)

        self.setGeometry(0, 0, self.W, self.H)
        self.roi = get_table_roi()                       # Rect initial
        self.dragging = False
        self.moving = False
        self.drag_start = QtCore.QPoint()
        self.move_offset = QtCore.QPoint()

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.drawPixmap(0, 0, self.pix)

        # overlay semi-transparent hors ROI
        p.setOpacity(0.35)
        overlay = QtGui.QColor(0, 0, 0)
        p.fillRect(self.rect(), overlay)
        p.setOpacity(1.0)

        # "trou" ROI
        roi_rect = QtCore.QRect(self.roi.x, self.roi.y, self.roi.w, self.roi.h)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(roi_rect, QtCore.Qt.GlobalColor.transparent)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)

        # contour ROI
        pen = QtGui.QPen(QtGui.QColor("#00E676"))  # vert
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRect(roi_rect)

        # instructions
        p.setPen(QtGui.QColor("#FFFFFF"))
        font = p.font(); font.setPointSize(12)
        p.setFont(font)
        p.drawText(20, 30, INSTR)
        p.end()

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            rx, ry, rw, rh = self.roi.x, self.roi.y, self.roi.w, self.roi.h
            if (rx <= ev.x() <= rx + rw) and (ry <= ev.y() <= ry + rh):
                self.moving = True
                self.move_offset = QtCore.QPoint(ev.x() - rx, ev.y() - ry)
            else:
                self.dragging = True
                self.drag_start = ev.position().toPoint()
                self.roi = Rect(self.drag_start.x(), self.drag_start.y(), 1, 1)
            self.update()

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent):
        if self.dragging:
            x0, y0 = self.drag_start.x(), self.drag_start.y()
            x1, y1 = ev.position().toPoint().x(), ev.position().toPoint().y()
            x = min(x0, x1); y = min(y0, y1)
            w = max(1, abs(x1 - x0)); h = max(1, abs(y1 - y0))
            self.roi = Rect(x, y, w, h)
            self.update()
        elif self.moving:
            nx = ev.x() - self.move_offset.x()
            ny = ev.y() - self.move_offset.y()
            nx = max(0, min(nx, self.W - self.roi.w))
            ny = max(0, min(ny, self.H - self.roi.h))
            self.roi = Rect(nx, ny, self.roi.w, self.roi.h)
            self.update()

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            self.dragging = False
            self.moving = False

    def keyPressEvent(self, ev: QtGui.QKeyEvent):
        k = ev.key()
        step = 1
        if k == QtCore.Qt.Key.Key_Left:
            self.roi = Rect(max(0, self.roi.x - step), self.roi.y, self.roi.w, self.roi.h)
        elif k == QtCore.Qt.Key.Key_Right:
            self.roi = Rect(min(self.W - self.roi.w, self.roi.x + step), self.roi.y, self.roi.w, self.roi.h)
        elif k == QtCore.Qt.Key.Key_Up:
            self.roi = Rect(self.roi.x, max(0, self.roi.y - step), self.roi.w, self.roi.h)
        elif k == QtCore.Qt.Key.Key_Down:
            self.roi = Rect(self.roi.x, min(self.H - self.roi.h, self.roi.y + step), self.roi.w, self.roi.h)
        elif k == QtCore.Qt.Key.Key_R:  # reset
            self.roi = Rect(100, 100, 1280, 720)
        elif k == QtCore.Qt.Key.Key_V:  # preview
            crop_img = crop(self.img, self.roi)
            bgr = cv2.cvtColor(crop_img, cv2.COLOR_RGB2BGR)
            cv2.imshow("Preview ROI", bgr)
            cv2.waitKey(1)
        elif k == QtCore.Qt.Key.Key_S:  # save
            set_table_roi(self.roi, ACTIVE_ROOM)
            QtWidgets.QMessageBox.information(self, "Sauvegardé",
                    f"ROI enregistrée pour '{ACTIVE_ROOM}': {self.roi}")
        elif k == QtCore.Qt.Key.Key_Escape:
            self.close()
        self.update()

def run_calibrator():
    app = QtWidgets.QApplication([])
    w = Calibrator()
    w.showFullScreen()
    app.exec()
