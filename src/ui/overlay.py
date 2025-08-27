# src/ui/overlay.py
from PySide6 import QtCore, QtGui, QtWidgets
import os, time

from src.state.builder import build_state
from src.ocr.engine_singleton import get_engine
from src.featurize.features import featurize
from src.policy.ollama_client import ask_policy
from src.policy.postprocess import finalize_action
from src.runtime.window_lock import LOCK  # ← ajout demandé

# ---------- Config ----------
REFRESH_MS        = int(os.getenv("POKERIA_REFRESH_MS", "1000"))  # 1s par défaut
POLICY_PERIOD_S   = float(os.getenv("POKERIA_POLICY_PERIOD", "2.5"))
MANUAL_ONLY       = os.getenv("POKERIA_MANUAL_ONLY", "0") == "1"          # démarre en mode MANUEL si 1
FOLLOW_ROI        = os.getenv("POKERIA_OVERLAY_FOLLOW_ROI", "1") == "1"   # suit la table si possible
COLORBLIND        = os.getenv("POKERIA_COLORBLIND", "0") == "1"           # palette daltonisme

PALETTE_DEFAULT = {
    "raise":   {"accent": "#16a34a"},
    "call":    {"accent": "#f59e0b"},
    "check":   {"accent": "#38bdf8"},
    "fold":    {"accent": "#ef4444"},
    "all-in":  {"accent": "#a21caf"},
    "none":    {"accent": "#9ca3af"},
}
PALETTE_CB = {  # daltonisme
    "raise":   {"accent": "#3b82f6"},
    "call":    {"accent": "#fb923c"},
    "check":   {"accent": "#a78bfa"},
    "fold":    {"accent": "#6b7280"},
    "all-in":  {"accent": "#f472b6"},
    "none":    {"accent": "#9ca3af"},
}
PALETTE = PALETTE_CB if COLORBLIND else PALETTE_DEFAULT


# ---------- Worker (OCR + IA conditionnelle) ----------
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

        # ----- Garde-fou foreground/minimized -----
        from src.runtime.window_lock import LOCK  # ← demandé
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
                self.finished.emit()
                return
        # -----------------------------------------

        try:
            eng = get_engine()
            st = build_state(engine=eng)

            # Prépare l'affichage état
            hero    = st.hero_cards[:]
            board   = st.community_cards[:]
            pot     = float(getattr(st, "pot_size", 0.0) or 0.0)
            stack   = float(getattr(st, "hero_stack", 0.0) or 0.0)
            to_call = float(getattr(st, "to_call", 0.0) or 0.0)
            dealer  = getattr(st, "dealer_seat", None)

            # Signature d'état
            sig = f"{' '.join(hero)}|{' '.join(board)}|{to_call:.2f}|{pot:.2f}"

            # Debug ROIs (si dispo)
            debug_rois = []
            if self.want_debug_rois:
                try:
                    # attendu: [(x,y,w,h,label), ...] en coords écran
                    debug_rois = eng.get_debug_rois()
                except Exception:
                    debug_rois = []

            # ROI/table rect (pour follow ROI)
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

            # Décide si on appelle la policy ici
            do_policy = self.force_policy or (self.allow_policy and (sig != self.last_sig) and len(hero) >= 2)

            action = None
            policy_ms = 0.0
            if do_policy:
                pol_t0 = time.perf_counter()
                x, _, dbg = featurize(st)
                dbg["hero_cards"] = hero
                dbg["board_cards"] = board
                dbg["pot_size"]    = pot
                dbg["hero_stack"]  = stack
                dbg["to_call"]     = to_call
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


# ---------- Overlay UI ----------
class Overlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        # ⚠️ pas de AA_UseSoftwareOpenGL ici (on le met dans run() avant QApplication)

        # ----- Bandeau statut (init + refresh immédiat) -----
        self.win_status = QtWidgets.QLabel(self)
        self.win_status.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.win_status.setStyleSheet("color: white; background: rgba(0,0,0,120); padding: 3px; font-size: 11px;")
        self.win_status.move(12, 8)
        self.win_status.resize(900, 22)

        # Raccourcis fenêtres F6/F7
        QtGui.QShortcut(QtGui.QKeySequence("F6"), self, activated=self.on_cycle_window)
        QtGui.QShortcut(QtGui.QKeySequence("F7"), self, activated=self.on_toggle_lock)

        # Rafraîchir la liste tout de suite (pour éviter unknown/none)
        try:
            LOCK.refresh()
        except Exception:
            pass

        # Timer statut périodique
        self.status_timer = QtCore.QTimer(self)
        self.status_timer.setInterval(400)
        self.status_timer.timeout.connect(self._tick_win_status)
        self.status_timer.start()
        # ----------------------------------------------------

        self.setWindowTitle("PokerIA HUD")
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # Translucide / Opaque
        if os.getenv("POKERIA_OVERLAY_OPAQUE", "0") == "1":
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
            self.setWindowOpacity(0.98)
            panel_bg = "background: rgba(0,0,0,0.70);"
        else:
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            panel_bg = "background: rgba(0,0,0,0.35);"

        # Click-through (ToS-safe)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        # Plein écran par défaut (suivi table ensuite si activé)
        self._set_fullscreen_geometry()

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
        self.mode_lbl = L(); self.perf_lbl = L()

        panel = QtWidgets.QFrame()
        panel.setStyleSheet(f"{panel_bg} border-radius: 12px;")
        v = QtWidgets.QVBoxLayout(panel); v.setContentsMargins(16,16,12,12); v.setSpacing(6)
        for w in [self.mode_lbl, self.hero, self.board, self.pot, self.stack, self.tocall, self.dealer, self.action, self.status, self.perf_lbl]:
            v.addWidget(w)

        # Barre de confiance (fine)
        self.confbar = QtWidgets.QProgressBar()
        self.confbar.setTextVisible(False)
        self.confbar.setRange(0, 100)
        self.confbar.setFixedHeight(6)
        self.confbar.setStyleSheet(
            "QProgressBar{background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.18); border-radius: 3px;}"
            "QProgressBar::chunk{background: rgba(255,255,255,0.45); border-radius: 3px;}"
        )
        v.addWidget(self.confbar)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20,20,20,20)
        root.addWidget(panel, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        # Réfs de style pour appliquer la couleur selon l'action
        self.panel = panel
        self._panel_bg_style = panel.styleSheet()

        # Hotkeys HUD
        self.shortcut_show  = QtGui.QShortcut(QtGui.QKeySequence("F8"), self)
        self.shortcut_show.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcut_show.activated.connect(self.toggle_visible)

        self.shortcut_pause = QtGui.QShortcut(QtGui.QKeySequence("F9"), self)
        self.shortcut_pause.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcut_pause.activated.connect(self.toggle_pause)

        self.shortcut_force = QtGui.QShortcut(QtGui.QKeySequence("F10"), self)  # Demander conseil maintenant
        self.shortcut_force.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcut_force.activated.connect(self.ask_now)

        self.shortcut_mode  = QtGui.QShortcut(QtGui.QKeySequence("F11"), self)  # AUTO <-> MANUEL
        self.shortcut_mode.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcut_mode.activated.connect(self.toggle_mode)

        # Debug ROIs sur F5 (libère F7 pour lock)
        self.shortcut_rois  = QtGui.QShortcut(QtGui.QKeySequence("F5"), self)
        self.shortcut_rois.setContext(QtCore.Qt.ApplicationShortcut)
        self.shortcut_rois.activated.connect(self.toggle_rois)

        # État interne
        self.paused = False
        self.busy = False
        self.last_policy_ts = 0.0
        self.last_sig = ""
        self.force_policy_once = False
        self.auto_mode = not MANUAL_ONLY
        self.show_rois = False
        self._debug_rois = []        # pour paintEvent
        self._last_table_rect = None # suivi de table
        self._policy_cache = {}      # sig -> action

        self._refresh_mode_label()
        self._tick_win_status(force=True)  # refresh immédiat

        # Timer UI (tick principal pour OCR/policy)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(REFRESH_MS)

    # ------- geometry helpers -------
    def _set_fullscreen_geometry(self):
        screen_geo = QtGui.QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen_geo)

    def _maybe_follow_roi(self, table_rect):
        if not FOLLOW_ROI or not table_rect:
            return
        try:
            x, y, w, h = table_rect
            self.setGeometry(x, y, w, h)
        except Exception:
            pass

    # ------- actions UI -------
    @QtCore.Slot()
    def toggle_visible(self):
        self.setVisible(not self.isVisible())

    @QtCore.Slot()
    def toggle_pause(self):
        self.paused = not self.paused
        self.status.setText("⏸️ Pause" if self.paused else "")

    @QtCore.Slot()
    def ask_now(self):
        self.force_policy_once = True
        self.status.setText("⏳ Demande de conseil…")

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

    def _refresh_mode_label(self):
        self.mode_lbl.setText("Mode: " + ("AUTO" if self.auto_mode else "MANUEL"))

    # ------- cycle -------
    @QtCore.Slot()
    def tick(self):
        if self.paused or self.busy:
            return
        self.busy = True

        # throttle LLM en mode AUTO; en MANUEL jamais (sauf force)
        allow_policy = False
        now = time.monotonic()
        if self.auto_mode:
            allow_policy = (now - self.last_policy_ts) >= POLICY_PERIOD_S

        force_policy = self.force_policy_once
        self.force_policy_once = False  # reset

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
        # Suivre table si possible (via worker)
        if res.table_rect:
            self._last_table_rect = res.table_rect
            self._maybe_follow_roi(res.table_rect)

        # Maj labels d'état
        self.hero.setText("Hero: " + (" ".join(res.hero) if res.hero else "—"))
        self.board.setText("Board: " + (" ".join(res.board) if res.board else "—"))
        self.pot.setText(f"Pot: {res.pot:.2f} €")
        self.stack.setText(f"Stack H: {res.stack:.2f} €")
        self.tocall.setText(f"A suivre: {res.to_call:.2f} €")
        self.dealer.setText(f"BTN seat: {res.dealer if res.dealer is not None else '—'}")

        # Choix action : policy du worker OU cache
        a = None
        if res.action:
            a = res.action
            self._policy_cache[res.signature] = a
            self.last_policy_ts = time.monotonic()
        else:
            a = self._policy_cache.get(res.signature)

        self.last_sig = res.signature

        # Affichage action + thème couleur + confiance
        if not a:
            self.action.setText("Action: —")
            self._apply_action_theme("none", 0.0)
        else:
            typ = a.get("type", "none")
            sz  = float(a.get("size_bb", 0.0) or 0.0)
            pr  = float(a.get("percent", 0.0) or 0.0)
            cf  = float(a.get("confidence", 0.0) or 0.0)

            text = f"Action: {typ.upper()}"
            if typ == "call" and res.to_call > 0:
                text += f"  ({sz:.2f} bb)"
            if typ == "raise":
                text += f"  ({sz:.2f} bb ~ {int(pr*100)}% pot)"
            text += f"   conf={int(cf*100)}%"
            self.action.setText(text)

            self._apply_action_theme(typ, cf)

        # Status
        if res.policy_queried:
            self.status.setText("✅ Conseil mis à jour")
        else:
            self.status.setText("")

        # Perf
        self.perf_lbl.setText(
            f"⏱ OCR {res.ocr_ms:.0f} ms" + (f" • IA {res.policy_ms:.0f} ms" if res.policy_ms else "")
        )

        # Debug ROIs
        self._debug_rois = res.debug_rois if isinstance(res.debug_rois, list) else []
        if self.show_rois:
            self.update()

    @QtCore.Slot(str)
    def on_error(self, msg: str):
        self.status.setText(f"ERR: {msg}")

    # ------- thème couleur + confiance -------
    def _apply_action_theme(self, typ: str, conf: float):
        key = (typ or "none").lower()
        if key not in PALETTE:
            key = "none"
        color = PALETTE[key]["accent"]

        # Bordure colorée + fond conservé
        self.panel.setStyleSheet(
            f"{self._panel_bg_style} border-left: 4px solid {color};"
        )

        # Jauge de confiance
        pct = max(0, min(int(conf * 100), 100))
        self.confbar.setValue(pct)
        self.confbar.setStyleSheet(
            "QProgressBar{background: rgba(255,255,255,0.12); "
            "border: 1px solid rgba(255,255,255,0.18); border-radius: 3px;}"
            f"QProgressBar::chunk{{background: {color}; border-radius: 3px;}}"
        )

        # Texte: garder blanc (lisibilité sur fond sombre)
        self.action.setStyleSheet("color: white;")

    # ------- dessin overlay (debug ROIs) -------
    def paintEvent(self, ev):
        super().paintEvent(ev)
        if not self.show_rois or not self._debug_rois:
            return
        qp = QtGui.QPainter(self)
        qp.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtCore.Qt.green)
        pen.setWidth(2)
        qp.setPen(pen)
        for roi in self._debug_rois:
            try:
                x, y, w, h, label = roi
            except Exception:
                continue
            qp.drawRect(int(x), int(y), int(w), int(h))
            qp.drawText(int(x)+3, int(y)+14, str(label))
        qp.end()

    # ------- Fenêtrage / LOCK (raccourcis + statut) -------
    @QtCore.Slot()
    def on_cycle_window(self):
        LOCK.cycle()
        self._tick_win_status(force=True)

    @QtCore.Slot()
    def on_toggle_lock(self):
        LOCK.toggle_lock()
        self._tick_win_status(force=True)

    def _tick_win_status(self, force: bool=False):
        st = LOCK.get_status()
        paused = False
        paused_reason = ""
        if os.getenv("POKERIA_REQUIRE_FOREGROUND","1") == "1":
            try:
                if LOCK.is_minimized():
                    paused = True; paused_reason = "minimized"
                elif st.locked and not LOCK.is_foreground():
                    paused = True; paused_reason = "not foreground"
            except Exception:
                pass

        status = "LOCKED" if getattr(st, "locked", False) else "FOLLOW"
        if paused:
            status += f" | PAUSED ({paused_reason})"

        room = getattr(st, "room", "?")
        title = (getattr(st, "title", "") or "")[:80]
        self.win_status.setText(f"Room: {room} | Window: {title} | {status}")

        if force:
            self.update()


def run():
    # ✅ Forcer OpenGL logiciel AVANT la création de QApplication
    if os.getenv("POKERIA_USE_SOFTGL", "1") == "1":
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseSoftwareOpenGL, True)

    app = QtWidgets.QApplication([])
    w = Overlay()
    w.show()
    app.exec()

if __name__ == "__main__":
    run()
