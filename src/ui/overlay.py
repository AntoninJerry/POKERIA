# src/ui/overlay.py
from PySide6 import QtCore, QtGui, QtWidgets
import os, time
from dataclasses import asdict

from src.state.builder import build_state
from src.ocr.engine_singleton import get_engine
from src.featurize.features import featurize
from src.policy.ollama_client import ask_policy
from src.policy.postprocess import finalize_action

REFRESH_MS = int(os.getenv("POKERIA_REFRESH_MS", "1200"))  # + lent = + fluide sur CPU
POLICY_PERIOD_S = float(os.getenv("POKERIA_POLICY_PERIOD", "2.5"))  # pas de LLM plus d’1 fois / 2.5s

# ---------- Worker en thread (OCR + IA) ----------
class WorkResult(QtCore.QObject):
    def __init__(self, **kw):
        super().__init__()
        for k, v in kw.items():
            setattr(self, k, v)

class Worker(QtCore.QObject):
    finished = QtCore.Signal()
    resultReady = QtCore.Signal(object)  # WorkResult
    error = QtCore.Signal(str)

    def __init__(self, want_policy: bool):
        super().__init__()
        self.want_policy = want_policy

    @QtCore.Slot()
    def run(self):
        try:
            eng = get_engine()
            st = build_state(engine=eng)

            # Prépare l'affichage état
            hero = st.hero_cards[:]
            board = st.community_cards[:]
            pot = float(st.pot_size)
            stack = float(st.hero_stack)
            to_call = float(st.to_call)
            dealer = st.dealer_seat if st.dealer_seat is not None else None

            # Par défaut: pas d'action
            action = {"type": "none", "size_bb": 0.0, "percent": 0.0, "confidence": 0.0, "rationale": ""}

            # IA seulement si on a 2 cartes
            if self.want_policy and len(hero) >= 2:
                x, _, dbg = featurize(st)
                dbg["hero_cards"] = hero
                dbg["board_cards"] = board
                dbg["pot_size"] = pot
                dbg["hero_stack"] = stack
                dbg["to_call"] = to_call
                raw = ask_policy(x, dbg)
                action = finalize_action(raw, dbg)

            self.resultReady.emit(WorkResult(hero=hero, board=board, pot=pot, stack=stack,
                                             to_call=to_call, dealer=dealer, action=action))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
        finally:
            self.finished.emit()

# ---------- Overlay UI ----------
class Overlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        # Option: forcer le rendu logiciel pour éviter écran noir (Intel/anciens drivers)
        if os.getenv("POKERIA_USE_SOFTGL", "1") == "1":
            # Doit être avant QApplication en théorie, mais on met aussi ici par sécurité
            QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseSoftwareOpenGL)

        self.setWindowTitle("Pokeria HUD")
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # Translucide (peut causer black screen sur certains PC) -> désactivable
        if os.getenv("POKERIA_OVERLAY_OPAQUE", "0") == "1":
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
            self.setWindowOpacity(0.98)
            panel_bg = "background: rgba(0,0,0,0.70);"
        else:
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            panel_bg = "background: rgba(0,0,0,0.35);"

        # Click-through (ToS-safe)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        # Fullscreen overlay
        screen_geo = QtGui.QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen_geo)

        # --- UI ---
        font_h = QtGui.QFont("Segoe UI", 12, QtGui.QFont.Bold)
        font_b = QtGui.QFont("Segoe UI", 11)

        def L(big=False):
            lbl = QtWidgets.QLabel("")
            lbl.setFont(font_h if big else font_b)
            lbl.setStyleSheet("color: white;")
            return lbl

        self.hero = L(True); self.board = L(True)
        self.pot = L(); self.stack = L(); self.tocall = L(); self.dealer = L()
        self.action = L(True); self.status = L()

        panel = QtWidgets.QFrame()
        panel.setStyleSheet(f"{panel_bg} border-radius: 12px;")
        v = QtWidgets.QVBoxLayout(panel); v.setContentsMargins(16,16,16,16); v.setSpacing(6)
        for w in [self.hero, self.board, self.pot, self.stack, self.tocall, self.dealer, self.action, self.status]:
            v.addWidget(w)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20,20,20,20)
        root.addWidget(panel, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        # Hotkeys
        self.shortcut_show  = QtGui.QShortcut(QtGui.QKeySequence("F8"), self)
        self.shortcut_show.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcut_show.activated.connect(self.toggle_visible)

        self.shortcut_pause = QtGui.QShortcut(QtGui.QKeySequence("F9"), self)
        self.shortcut_pause.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcut_pause.activated.connect(self.toggle_pause)

        self.paused = False
        self.busy = False
        self.last_policy_ts = 0.0

        # Timer UI
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(REFRESH_MS)

    # ------- actions UI -------
    @QtCore.Slot()
    def toggle_visible(self):
        self.setVisible(not self.isVisible())

    @QtCore.Slot()
    def toggle_pause(self):
        self.paused = not self.paused
        self.status.setText("⏸️ Pause" if self.paused else "")

    # ------- cycle -------
    @QtCore.Slot()
    def tick(self):
        if self.paused or self.busy:
            return
        self.busy = True

        # throttle LLM: 2.5s mini entre 2 appels (configurable)
        want_policy = (time.monotonic() - self.last_policy_ts) >= POLICY_PERIOD_S

        self.thread = QtCore.QThread(self)
        self.worker = Worker(want_policy=want_policy)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.resultReady.connect(self.on_result)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._unset_busy)
        self.thread.start()

    @QtCore.Slot()
    def _unset_busy(self):
        self.busy = False

    @QtCore.Slot(object)
    def on_result(self, res: WorkResult):
        # Etat
        self.hero.setText("Hero: " + (" ".join(res.hero) if res.hero else "—"))
        self.board.setText("Board: " + (" ".join(res.board) if res.board else "—"))
        self.pot.setText(f"Pot: {res.pot:.2f} €")
        self.stack.setText(f"Stack H: {res.stack:.2f} €")
        self.tocall.setText(f"A suivre: {res.to_call:.2f} €")
        self.dealer.setText(f"BTN seat: {res.dealer if res.dealer is not None else '—'}")

        # Action IA
        a = res.action.get("type", "none")
        sz = float(res.action.get("size_bb", 0.0) or 0.0)
        pr = float(res.action.get("percent", 0.0) or 0.0)
        cf = float(res.action.get("confidence", 0.0) or 0.0)

        if a in ("raise","call"):
            self.last_policy_ts = time.monotonic()  # on vient de consulter la policy

        text = f"Action: {a.upper()}"
        if a == "call" and res.to_call > 0:
            text += f"  ({sz:.2f} bb)"
        if a == "raise":
            text += f"  ({sz:.2f} bb ~ {int(pr*100)}% pot)"
        text += f"   conf={int(cf*100)}%"
        self.action.setText(text)
        self.status.setText("")

    @QtCore.Slot(str)
    def on_error(self, msg: str):
        self.status.setText(f"ERR: {msg}")

def run():
    # Astuce anti “écran noir” (forcer OpenGL logiciel avant l’app si besoin)
    if os.getenv("POKERIA_USE_SOFTGL", "1") == "1":
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseSoftwareOpenGL)
    app = QtWidgets.QApplication([])
    w = Overlay()
    w.show()
    app.exec()

if __name__ == "__main__":
    run()
