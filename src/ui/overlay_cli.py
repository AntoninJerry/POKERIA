# src/ui/overlay_compact.py — HUD carré stylé & léger
# --------------------------------------------------
# Petit panneau carré semi‑transparent, draggable/fermable, qui suit la table
# (offset configurable) et affiche l’essentiel: Hero, Board, Pot/ToCall, Action.
# Compatible avec le pipeline existant (engine/state/policy). 
#
# Raccourcis:
#   F4   : basculer mode interaction (drag/click)
#   F5   : afficher/masquer ROIs debug
#   F8   : cacher/afficher le HUD
#   F9   : pause/reprise OCR
#   F10  : forcer une requête policy immédiate
#   F11  : basculer AUTO/MANUEL (policy)
#   F12/Échap : fermer
#
# Variables d’env (optionnelles):
#   POKERIA_OVERLAY_FOLLOW_ROI=1      (suivre la table)
#   POKERIA_BOX_SIZE=260              (côté du carré en px)
#   POKERIA_BOX_OFFSET="16,16"        (dx,dy relatifs au coin supérieur gauche de la table)
#   POKERIA_PANEL_RGB="16,18,24"     (fond RGB)
#   POKERIA_PANEL_OPACITY=0.60        (opacité 0..1)
#   POKERIA_COLORBLIND=0/1            (palette dalto-friendly)
#   POKERIA_REFRESH_MS=800            (rafraîchissement OCR)
#   POKERIA_POLICY_PERIOD=2.5         (intervalle min entre 2 calls policy en AUTO)
#   POKERIA_REQUIRE_FOREGROUND=1      (pause si fenêtre poker non au premier plan)
#
from PySide6 import QtCore, QtGui, QtWidgets
import os, time

from src.state.builder import build_state
from src.ocr.engine_singleton import get_engine
from src.featurize.features import featurize
from src.policy.ollama_client import ask_policy
from src.policy.postprocess import finalize_action
from src.runtime.window_lock import LOCK

# ---------- Config ----------
REFRESH_MS      = int(os.getenv("POKERIA_REFRESH_MS", "800"))
POLICY_PERIOD_S = float(os.getenv("POKERIA_POLICY_PERIOD", "2.5"))
FOLLOW_ROI      = os.getenv("POKERIA_OVERLAY_FOLLOW_ROI", "1") == "1"
COLORBLIND  = os.getenv("POKERIA_COLORBLIND", "0") == "1"
ON_DEMAND = os.getenv("POKERIA_ON_DEMAND", "0") == "1"

PANEL_RGB_STR   = os.getenv("POKERIA_PANEL_RGB", "16,18,24")
try:
    _r,_g,_b = [int(x.strip()) for x in PANEL_RGB_STR.split(",")]
    _r=_r%256; _g=_g%256; _b=_b%256
except Exception:
    _r,_g,_b = (16,18,24)
try:
    _op = float(os.getenv("POKERIA_PANEL_OPACITY","0.60"))
    _op = max(0.0, min(_op, 1.0))
except Exception:
    _op = 0.60
PANEL_BG_CSS = f"background: rgba({_r},{_g},{_b},{_op});"

try:
    BOX_SIZE = int(os.getenv("POKERIA_BOX_SIZE", "260"))
    BOX_SIZE = max(200, min(BOX_SIZE, 400))
except Exception:
    BOX_SIZE = 260

try:
    _dx,_dy = [int(x.strip()) for x in os.getenv("POKERIA_BOX_OFFSET", "16,16").split(",")]
except Exception:
    _dx,_dy = (16,16)
BOX_OFFSET = (_dx, _dy)

PALETTE_DEFAULT = {
    "raise":  {"accent": "#16a34a"},
    "call":   {"accent": "#f59e0b"},
    "check":  {"accent": "#38bdf8"},
    "fold":   {"accent": "#ef4444"},
    "all-in": {"accent": "#a21caf"},
    "none":   {"accent": "#9ca3af"},
}
PALETTE_CB = {
    "raise":  {"accent": "#3b82f6"},
    "call":   {"accent": "#fb923c"},
    "check":  {"accent": "#a78bfa"},
    "fold":   {"accent": "#6b7280"},
    "all-in": {"accent": "#f472b6"},
    "none":   {"accent": "#9ca3af"},
}
PALETTE = PALETTE_CB if COLORBLIND else PALETTE_DEFAULT

# ---------- Worker (OCR + IA) ----------
class WorkResult(QtCore.QObject):
    def __init__(self, **kw):
        super().__init__()
        for k, v in kw.items():
            setattr(self, k, v)

class Worker(QtCore.QObject):
    finished    = QtCore.Signal()
    resultReady = QtCore.Signal(object)  # WorkResult
    error       = QtCore.Signal(str)

    def __init__(self, allow_policy: bool, last_sig: str, force_policy: bool, want_debug_rois: bool):
        super().__init__()
        self.allow_policy    = allow_policy
        self.last_sig        = last_sig
        self.force_policy    = force_policy
        self.want_debug_rois = want_debug_rois

    @QtCore.Slot()
    def run(self):
        ocr_t0 = time.perf_counter()
        # Garde‑fou: fenêtre poker visible/foreground si exigé
        if os.getenv("POKERIA_REQUIRE_FOREGROUND","1") == "1":
            st_lock = LOCK.get_status()
            if st_lock.locked and (LOCK.is_minimized() or not LOCK.is_foreground()):
                self.resultReady.emit(WorkResult(
                    hero=[], board=[], pot=0.0, stack=0.0, to_call=0.0, dealer=None,
                    action={"type":"none","size_bb":0.0,"percent":0.0,"confidence":0.0,"rationale":"paused"},
                    signature="(paused)", policy_queried=False,
                    ocr_ms=0.0, policy_ms=0.0,
                    debug_rois=[], table_rect=LOCK.get_rect()
                ))
                self.finished.emit(); return
        try:
            eng = get_engine()
            st  = build_state(engine=eng)

            hero    = st.hero_cards[:]
            board   = st.community_cards[:]
            pot     = float(getattr(st, "pot_size", 0.0) or 0.0)
            stack   = float(getattr(st, "hero_stack", 0.0) or 0.0)
            to_call = float(getattr(st, "to_call", 0.0) or 0.0)
            dealer  = getattr(st, "dealer_seat", None)

            sig = f"{' '.join(hero)}|{' '.join(board)}|{to_call:.2f}|{pot:.2f}"

            debug_rois = []
            if self.want_debug_rois:
                try:
                    debug_rois = eng.get_debug_rois()
                except Exception:
                    debug_rois = []

            table_rect = None
            try:
                if hasattr(eng, "get_table_rect"):
                    r = eng.get_table_rect()
                    table_rect = (int(r.left), int(r.top), int(r.width), int(r.height))
                elif hasattr(eng, "last_roi"):
                    r = eng.last_roi
                    table_rect = (int(r.left), int(r.top), int(r.width), int(r.height))
            except Exception:
                table_rect = None

            do_policy = self.force_policy or (self.allow_policy and (sig != self.last_sig) and len(hero) >= 2)

            action = None
            policy_ms = 0.0
            if do_policy:
                pol_t0 = time.perf_counter()
                x, _, dbg = featurize(st)
                dbg.update({
                    "hero_cards": hero, "board_cards": board,
                    "pot_size": pot, "hero_stack": stack, "to_call": to_call
                })
                raw = ask_policy(x, dbg)
                action = finalize_action(raw, dbg)
                policy_ms = (time.perf_counter() - pol_t0) * 1000.0

            ocr_ms = (time.perf_counter() - ocr_t0) * 1000.0

            self.resultReady.emit(WorkResult(
                hero=hero, board=board, pot=pot, stack=stack, to_call=to_call, dealer=dealer,
                action=action, signature=sig, policy_queried=bool(do_policy),
                ocr_ms=ocr_ms, policy_ms=policy_ms,
                debug_rois=debug_rois, table_rect=table_rect
            ))
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
        finally:
            self.finished.emit()

# ---------- HUD carré ----------
class CompactOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PokerIA HUD")
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        # Click‑through par défaut (sécurise la table). F4 pour activer l’interaction.
        self.interact_mode = False
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        # Géométrie: carré compact
        self.setFixedSize(BOX_SIZE, BOX_SIZE)
        self._place_default()

        # ---- Contenu ----
        font_h = QtGui.QFont("Segoe UI", 12, QtGui.QFont.Bold)
        font_b = QtGui.QFont("Segoe UI", 11)
        font_x = QtGui.QFont("Segoe UI", 14, QtGui.QFont.Black)

        def L(font=font_b, align=QtCore.Qt.AlignLeft):
            lbl = QtWidgets.QLabel("")
            lbl.setFont(font)
            lbl.setStyleSheet("color:white;")
            lbl.setAlignment(align)
            return lbl

        panel = QtWidgets.QFrame(self)
        panel.setObjectName("hudpanel")
        panel.setStyleSheet(f"QFrame#hudpanel{{{PANEL_BG_CSS} border-radius: 14px; border:1px solid rgba(255,255,255,0.12);}}")
        panel.setGeometry(0, 0, BOX_SIZE, BOX_SIZE)

        # Ombre douce (style glassy)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QtGui.QColor(0,0,0,120))
        panel.setGraphicsEffect(shadow)

        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Top bar (mode + perf court)
        self.mode_lbl = L(font_b)
        self.perf_lbl = L(QtGui.QFont("Segoe UI", 10))

        # Lignes infos
        self.hero  = L(font_h)
        self.board = L(font_h)
        info_grid = QtWidgets.QGridLayout(); info_grid.setContentsMargins(0,0,0,0); info_grid.setHorizontalSpacing(10); info_grid.setVerticalSpacing(4)
        self.pot   = L()
        self.tocall= L()
        self.stack = L()
        self.dealer= L()
        info_grid.addWidget(self.pot,   0,0); info_grid.addWidget(self.tocall,0,1)
        info_grid.addWidget(self.stack, 1,0); info_grid.addWidget(self.dealer,1,1)

        # Action principale
        self.action = L(font_x)
        self.action.setAlignment(QtCore.Qt.AlignCenter)

        # Barre de confiance
        self.confbar = QtWidgets.QProgressBar()
        self.confbar.setTextVisible(False)
        self.confbar.setRange(0, 100)
        self.confbar.setFixedHeight(8)
        self.confbar.setStyleSheet(
            "QProgressBar{background: rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.18); border-radius:4px;}"
            "QProgressBar::chunk{background: rgba(255,255,255,0.55); border-radius:4px;}"
        )

        lay.addWidget(self.mode_lbl)
        lay.addWidget(self.hero)
        lay.addWidget(self.board)
        lay.addLayout(info_grid)
        lay.addStretch(1)
        lay.addWidget(self.action)
        lay.addWidget(self.confbar)
        lay.addWidget(self.perf_lbl)

        self.panel = panel
        self._panel_bg_style = self.panel.styleSheet()

        # Titlebar (drag/close) visible seulement en mode interaction
        self._setup_titlebar()

        # Hotkeys
        QtGui.QShortcut(QtGui.QKeySequence("F8"),  self, activated=self.toggle_visible)
        QtGui.QShortcut(QtGui.QKeySequence("F9"),  self, activated=self.toggle_pause)
        QtGui.QShortcut(QtGui.QKeySequence("F10"), self, activated=self.ask_now)
        QtGui.QShortcut(QtGui.QKeySequence("F11"), self, activated=self.toggle_mode)
        QtGui.QShortcut(QtGui.QKeySequence("F5"),  self, activated=self.toggle_rois)
        QtGui.QShortcut(QtGui.QKeySequence("F4"),  self, activated=self.toggle_interact)
        QtGui.QShortcut(QtGui.QKeySequence("F12"), self, activated=self.close)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, activated=self.close)
        # Fenêtres/Lock comme l’overlay classique
        QtGui.QShortcut(QtGui.QKeySequence("F6"), self, activated=self.on_cycle_window)
        QtGui.QShortcut(QtGui.QKeySequence("F7"), self, activated=self.on_toggle_lock)

        # État
        self.paused = False
        self.busy   = False
        self.last_policy_ts = 0.0
        self.last_sig = ""
        self.force_policy_once = False
        self.auto_mode = True
        self.show_rois = False
        self._debug_rois = []
        self._last_table_rect = None
        self._policy_cache = {}

        self._refresh_mode_label()

        # Timer principal
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        if not ON_DEMAND:
            self.timer.start(REFRESH_MS)
        else:
            self.mode_lbl.setText("Veille — appuie sur Espace")
            QtGui.QShortcut(QtGui.QKeySequence("Space"), self, activated=self.run_once)
            QtCore.QTimer.singleShot(80, self._warmup)

    # ----- helpers géométrie -----
    def _place_default(self):
        # Par défaut: coin haut-gauche de l’écran
        screen_geo = QtGui.QGuiApplication.primaryScreen().geometry()
        self.move(screen_geo.left()+20, screen_geo.top()+20)

    def _maybe_follow_roi(self, table_rect):
        if not FOLLOW_ROI or not table_rect:
            return
        try:
            x, y, w, h = table_rect
            dx, dy = BOX_OFFSET
            # Place dans le coin haut-gauche de la table, avec offset
            self.move(x + dx, y + dy)
        except Exception:
            pass

    # ----- titlebar/interaction -----
    def _setup_titlebar(self):
        self.titlebar = QtWidgets.QFrame(self)
        self.titlebar.setObjectName("titlebar")
        self.titlebar.setFixedHeight(28)
        self.titlebar.setStyleSheet(
            "QFrame#titlebar{background: rgba(255,255,255,0.08); border-radius: 8px;}"
            "QLabel{color:white; font-size:12px; padding-left:8px;}"
            "QPushButton{color:white; background:transparent; border:none; font-size:14px; padding:2px 8px;}"
            "QPushButton:hover{background: rgba(255,255,255,0.15); border-radius: 6px;}"
        )
        self.titlebar.setVisible(False)
        lay = QtWidgets.QHBoxLayout(self.titlebar)
        lay.setContentsMargins(8,2,6,2); lay.setSpacing(6)
        self.drag_lbl = QtWidgets.QLabel("⠿ Déplacer")
        lay.addWidget(self.drag_lbl); lay.addStretch(1)
        btn_close = QtWidgets.QPushButton("×"); btn_close.clicked.connect(self.close)
        lay.addWidget(btn_close)
        self.titlebar.installEventFilter(self)
        self._drag_active = False
        self._drag_offset = QtCore.QPoint()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        w = 160
        self.titlebar.setFixedWidth(w)
        self.titlebar.move(self.width() - w - 8, 8)

    def eventFilter(self, obj, ev):
        if obj is self.titlebar and self.interact_mode:
            if ev.type() == QtCore.QEvent.MouseButtonPress and ev.button() == QtCore.Qt.LeftButton:
                self._drag_active = True
                gp = ev.globalPosition().toPoint() if hasattr(ev, "globalPosition") else ev.globalPos()
                self._drag_offset = gp - self.frameGeometry().topLeft()
                return True
            if ev.type() == QtCore.QEvent.MouseMove and self._drag_active:
                gp = ev.globalPosition().toPoint() if hasattr(ev, "globalPosition") else ev.globalPos()
                self.move(gp - self._drag_offset)
                return True
            if ev.type() == QtCore.QEvent.MouseButtonRelease:
                self._drag_active = False
                return True
        return super().eventFilter(obj, ev)

    @QtCore.Slot()
    def toggle_interact(self):
        self.interact_mode = not self.interact_mode
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, not self.interact_mode)
        self.titlebar.setVisible(self.interact_mode)

    # ----- Lock/Windows -----
    @QtCore.Slot()
    def on_cycle_window(self):
        LOCK.cycle()

    @QtCore.Slot()
    def on_toggle_lock(self):
        LOCK.toggle_lock()

    # ----- UI dynamics -----
    def _refresh_mode_label(self):
        self.mode_lbl.setText("Mode: " + ("AUTO" if self.auto_mode else "MANUEL"))

    @QtCore.Slot()
    def toggle_visible(self):
        self.setVisible(not self.isVisible())

    @QtCore.Slot()
    def toggle_pause(self):
        self.paused = not self.paused
        self.mode_lbl.setText(("⏸ Pause — " if self.paused else "") + ("AUTO" if self.auto_mode else "MANUEL"))

    @QtCore.Slot()
    def ask_now(self):
        self.force_policy_once = True
        self.mode_lbl.setText("⏳ Demande de conseil…")

    @QtCore.Slot()
    def toggle_mode(self):
        self.auto_mode = not self.auto_mode
        self._refresh_mode_label()

    @QtCore.Slot()
    def toggle_rois(self):
        self.show_rois = not self.show_rois
        if not self.show_rois:
            self._debug_rois = []
        self.update()

    # ----- Loop principal -----
    @QtCore.Slot()
    def tick(self):
        if self.paused or self.busy:
            return
        self._run_worker(allow_auto=True, force_policy=False)

    def run_once(self):
        if self.busy:
            return
        self._run_worker(allow_auto=False, force_policy=True)

    def _run_worker(self, allow_auto: bool, force_policy: bool):
        self.busy = True
        allow_policy = False
        now = time.monotonic()
        if allow_auto and self.auto_mode:
            allow_policy = (now - self.last_policy_ts) >= POLICY_PERIOD_S
        if force_policy:
            allow_policy = True

        self.thread = QtCore.QThread(self)
        self.worker = Worker(
            allow_policy=allow_policy,
            last_sig=self.last_sig,
            force_policy=force_policy,
            want_debug_rois=self.show_rois
        )
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
        if res.table_rect:
            self._last_table_rect = res.table_rect
            self._maybe_follow_roi(res.table_rect)

        self.hero.setText("Hero: " + (" ".join(res.hero) if res.hero else "—"))
        self.board.setText("Board: " + (" ".join(res.board) if res.board else "—"))
        self.pot.setText(f"Pot: {res.pot:.2f} €")
        self.tocall.setText(f"À suivre: {res.to_call:.2f} €")
        self.stack.setText(f"Stack: {res.stack:.2f} €")
        self.dealer.setText(f"BTN: {res.dealer if res.dealer is not None else '—'}")

        a = None
        if res.action:
            a = res.action
            self._policy_cache[res.signature] = a
            self.last_policy_ts = time.monotonic()
        else:
            a = self._policy_cache.get(res.signature)
        self.last_sig = res.signature

        if not a:
            self.action.setText("—")
            self._apply_action_theme("none", 0.0)
        else:
            typ = a.get("type", "none").lower()
            sz  = float(a.get("size_bb", 0.0) or 0.0)
            pr  = float(a.get("percent", 0.0) or 0.0)
            cf  = float(a.get("confidence", 0.0) or 0.0)

            txt = typ.upper()
            if typ == "call" and res.to_call > 0:
                txt += f"  ({sz:.2f} bb)"
            if typ == "raise":
                txt += f"  ({sz:.2f} bb ~ {int(pr*100)}% pot)"
            txt += f"  • {int(cf*100)}%"
            self.action.setText(txt)
            self._apply_action_theme(typ, cf)

        self.perf_lbl.setText(f"⏱ OCR {res.ocr_ms:.0f} ms" + (f" • IA {res.policy_ms:.0f} ms" if res.policy_ms else ""))

        self._debug_rois = res.debug_rois if isinstance(res.debug_rois, list) else []
        if self.show_rois:
            self.update()

    @QtCore.Slot(str)
    def on_error(self, msg: str):
        self.perf_lbl.setText(f"ERR: {msg}")

    # ----- thème/action -----
    def _apply_action_theme(self, typ: str, conf: float):
        key = (typ or "none").lower()
        if key not in PALETTE:
            key = "none"
        color = PALETTE[key]["accent"]
        self.panel.setStyleSheet(f"{self._panel_bg_style} border-left:4px solid {color};")
        pct = max(0, min(int(conf * 100), 100))
        self.confbar.setValue(pct)
        self.confbar.setStyleSheet(
            "QProgressBar{background: rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.18); border-radius:4px;}"
            f"QProgressBar::chunk{{background: {color}; border-radius:4px;}}"
        )

    # ----- debug ROIs -----
    def _warmup(self):
        try:
            eng = get_engine()
            if hasattr(eng, "warmup"):
                eng.warmup()
        except Exception:
            pass
    def paintEvent(self, ev):
        super().paintEvent(ev)
        if not self.show_rois or not self._debug_rois:
            return
        qp = QtGui.QPainter(self)
        qp.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtCore.Qt.green); pen.setWidth(2); qp.setPen(pen)
        for roi in self._debug_rois:
            try:
                x, y, w, h, label = roi
            except Exception:
                continue
            # ne dessine que si ROI intersecte notre carré (en relatif simplifié)
            qp.drawRect(int(x), int(y), int(w), int(h))
            qp.drawText(int(x)+3, int(y)+14, str(label))
        qp.end()

# ---------- Entrée ----------
def run():
    if os.getenv("POKERIA_USE_SOFTGL", "1") == "1":
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseSoftwareOpenGL, True)
    app = QtWidgets.QApplication([])
    # Rafraîchit le LOCK au boot
    try:
        LOCK.refresh()
    except Exception:
        pass
    w = CompactOverlay()
    w.show()
    app.exec()

if __name__ == "__main__":
    run()
