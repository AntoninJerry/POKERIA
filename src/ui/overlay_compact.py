# src/ui/overlay_compact.py — HUD carré stylé & léger (ON-DEMAND)
# ----------------------------------------------------------------
# Panneau carré semi‑transparent, draggable/fermable, qui suit la table
# et affiche l’essentiel: Hero, Board, Pot/ToCall, Action + barre de confiance.
# Mode "à la demande" : pas de boucle continue, on presse Espace pour lancer
# une seule passe OCR (+ IA). Loader visible pendant l’attente.
#
# Raccourcis:
#   Space         : OCR + IA (une passe)
#   Shift+Space   : OCR seul
#   F4            : basculer mode interaction (drag/click)
#   F5            : afficher/masquer ROIs debug
#   F6 / F7       : cycle fenêtre / lock/unlock (LOCK)
#   F8            : cacher/afficher le HUD
#   F9            : pause/reprise (si timer actif)
#   F10           : forcer une requête policy immédiate
#   F11           : basculer AUTO/MANUEL (policy)
#   F12 / Échap   : fermer
#   F3            : basculer mode détaillé
#
# Variables d’env (optionnelles):
#   POKERIA_ON_DEMAND=1            (désactive la boucle, Espace déclenche)
#   POKERIA_OVERLAY_FOLLOW_ROI=1   (suivre la table)
#   POKERIA_BOX_SIZE=260           (côté du carré)
#   POKERIA_BOX_OFFSET="16,16"     (dx,dy relatifs au coin table)
#   POKERIA_PANEL_RGB="16,18,24"  (fond RGB)
#   POKERIA_PANEL_OPACITY=0.60     (0..1)
#   POKERIA_COLORBLIND=0/1         (palette dalto-friendly)
#   POKERIA_REFRESH_MS=800         (si ON_DEMAND=0)
#   POKERIA_POLICY_PERIOD=2.5      (intervalle min en AUTO)
#   POKERIA_REQUIRE_FOREGROUND=1   (pause si fenêtre poker pas au 1er plan)
#   POKERIA_THEME=default          (default, light, dark, green)

from PySide6 import QtCore, QtGui, QtWidgets
import os, time, json
from pathlib import Path

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
COLORBLIND      = os.getenv("POKERIA_COLORBLIND", "0") == "1"
ON_DEMAND       = os.getenv("POKERIA_ON_DEMAND", "1") == "1"  # par défaut ON

# Configuration des thèmes
THEME_COLORS = {
    "default": {"bg": "16,18,24", "text": "white", "border": "255,255,255,0.12"},
    "light": {"bg": "240,240,240", "text": "16,18,24", "border": "0,0,0,0.12"},
    "dark": {"bg": "16,18,24", "text": "white", "border": "255,255,255,0.12"},
    "green": {"bg": "23,30,24", "text": "200,200,200", "border": "46,125,50,0.12"}
}

theme_name = os.getenv("POKERIA_THEME", "default")
theme = THEME_COLORS.get(theme_name, THEME_COLORS["default"])

PANEL_RGB_STR   = os.getenv("POKERIA_PANEL_RGB", theme["bg"])
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
PANEL_BG_CSS = f"background: rgba({_r},{_g},{_b},{_op}); color: {theme['text']};"

try:
    BOX_SIZE = int(os.getenv("POKERIA_BOX_SIZE", "260"))
    BOX_SIZE = max(200, min(BOX_SIZE, 420))
except Exception:
    BOX_SIZE = 260

try:
    _dx,_dy = [int(x.strip()) for x in os.getenv("POKERIA_BOX_OFFSET", "16,16").split(",")]
except Exception:
    _dx,_dy = (16,16)
BOX_OFFSET = (_dx, _dy)

PALETTE_DEFAULT = {
    "raise":  {"accent": "#16a34a", "icon": "▲"},
    "call":   {"accent": "#f59e0b", "icon": "●"},
    "check":  {"accent": "#38bdf8", "icon": "✔"},
    "fold":   {"accent": "#ef4444", "icon": "✕"},
    "all-in": {"accent": "#a21caf", "icon": "⚡"},
    "none":   {"accent": "#9ca3af", "icon": "?"},
}
PALETTE_CB = {
    "raise":  {"accent": "#3b82f6", "icon": "▲"},
    "call":   {"accent": "#fb923c", "icon": "●"},
    "check":  {"accent": "#a78bfa", "icon": "✔"},
    "fold":   {"accent": "#6b7280", "icon": "✕"},
    "all-in": {"accent": "#f472b6", "icon": "⚡"},
    "none":   {"accent": "##9ca3af", "icon": "?"},
}
PALETTE = PALETTE_CB if COLORBLIND else PALETTE_DEFAULT

# ---------- Player Logger (conforme au cahier des charges) ----------
class PlayerLogger:
    def __init__(self):
        self.log_dir = Path.home() / ".pokeria" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.player_data = {}
        
    def log_action(self, player_name, action, amount=None, position=None, hand_strength=None):
        if player_name not in self.player_data:
            self.player_data[player_name] = {
                "actions": [],
                "stats": {
                    "vpip": 0,
                    "pfr": 0,
                    "aggression_factor": 0,
                    "preflop_raise": 0,
                    "hands_observed": 0
                }
            }
        
        # Enregistrer l'action
        log_entry = {
            "timestamp": time.time(),
            "action": action,
            "amount": amount,
            "position": position,
            "hand_strength": hand_strength
        }
        
        self.player_data[player_name]["actions"].append(log_entry)
        self.player_data[player_name]["stats"]["hands_observed"] += 1
        
        # Sauvegarder périodiquement
        if len(self.player_data[player_name]["actions"]) % 10 == 0:
            self.save_data()
    
    def save_data(self):
        """Sauvegarde les données des joueurs dans un fichier JSON"""
        try:
            with open(self.log_dir / "player_profiles.json", "w") as f:
                json.dump(self.player_data, f, indent=2)
        except Exception as e:
            print(f"Erreur sauvegarde logs: {e}")

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

    def __init__(self, allow_policy: bool, last_sig: str, force_policy: bool, want_debug_rois: bool, player_logger: PlayerLogger):
        super().__init__()
        self.allow_policy    = allow_policy
        self.last_sig        = last_sig
        self.force_policy    = force_policy
        self.want_debug_rois = want_debug_rois
        self.player_logger   = player_logger

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
                    debug_rois=[], table_rect=LOCK.get_rect(),
                    players_count=0, blinds=(0, 0), player_actions={}
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
            players_count = getattr(st, "players_count", 0)
            blinds = getattr(st, "blinds", (0, 0))
            player_actions = getattr(st, "player_actions", {})

            # Loguer les actions des joueurs
            for player, action_info in player_actions.items():
                self.player_logger.log_action(
                    player, 
                    action_info.get('action'), 
                    action_info.get('amount'),
                    action_info.get('position'),
                    action_info.get('hand_strength')
                )

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
                    "pot_size": pot, "hero_stack": stack, "to_call": to_call,
                    "players_count": players_count, "blinds": blinds
                })
                raw = ask_policy(x, dbg)
                action = finalize_action(raw, dbg)
                policy_ms = (time.perf_counter() - pol_t0) * 1000.0

            ocr_ms = (time.perf_counter() - ocr_t0) * 1000.0

            self.resultReady.emit(WorkResult(
                hero=hero, board=board, pot=pot, stack=stack, to_call=to_call, dealer=dealer,
                action=action, signature=sig, policy_queried=bool(do_policy),
                ocr_ms=ocr_ms, policy_ms=policy_ms,
                debug_rois=debug_rois, table_rect=table_rect,
                players_count=players_count, blinds=blinds, player_actions=player_actions
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
        
        # Modifier les flags de la fenêtre pour résoudre les problèmes d'affichage
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | 
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool  # Ajout du flag Tool pour éviter certains problèmes
        )
        
        # Essayer une approche différente pour la transparence
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        
        # Pour Windows, essayer d'utiliser WA_PaintOnScreen
        try:
            self.setAttribute(QtCore.Qt.WA_PaintOnScreen, True)
        except:
            pass

        # Click‑through par défaut (sécurise la table). F4 pour activer l’interaction.
        self.interact_mode = False
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        # Géométrie: carré compact
        self.setFixedSize(BOX_SIZE, BOX_SIZE)
        self._place_default()

        # Initialiser le logger joueurs
        self.player_logger = PlayerLogger()

        # ---- Contenu ----
        font_h = QtGui.QFont("Segoe UI", 12, QtGui.QFont.Bold)
        font_b = QtGui.QFont("Segoe UI", 11)
        font_x = QtGui.QFont("Segoe UI", 14, QtGui.QFont.Black)

        def L(font=font_b, align=QtCore.Qt.AlignLeft):
            lbl = QtWidgets.QLabel("")
            lbl.setFont(font)
            lbl.setStyleSheet("color:" + theme["text"] + "; background:transparent;")
            lbl.setAlignment(align)
            return lbl

        # Utiliser un widget conteneur avec layout au lieu de QFrame
        panel = QtWidgets.QWidget(self)
        panel.setObjectName("hudpanel")
        panel.setStyleSheet(f"QWidget#hudpanel{{{PANEL_BG_CSS} border-radius: 14px; border:1px solid rgba({theme['border']});}}")
        panel.setGeometry(0, 0, BOX_SIZE, BOX_SIZE)

        # Ombre douce (style glassy)
        shadow = QtWidgets.QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(18)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QtGui.QColor(0,0,0,120))
        panel.setGraphicsEffect(shadow)

        lay = QtWidgets.QVBoxLayout(panel)
        # Augmenter les marges et l'espacement pour un meilleur rendu
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)  # Augmenté de 6 à 8 pour plus d'espace

        # Indicateur de statut
        status_layout = QtWidgets.QHBoxLayout()
        self.status_indicator = QtWidgets.QFrame()
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.setStyleSheet("background-color: #16a34a; border-radius: 6px;")
        self.status_message = L(QtGui.QFont("Segoe UI", 9))
        status_layout.addWidget(self.status_indicator)
        status_layout.addWidget(self.status_message)
        status_layout.addStretch(1)

        # Top bar (mode + perf court)
        self.mode_lbl = L(font_b)
        self.perf_lbl = L(QtGui.QFont("Segoe UI", 10))

        # Lignes infos
        self.hero  = L(font_h)
        self.board = L(font_h)
        info_grid = QtWidgets.QGridLayout()
        info_grid.setContentsMargins(0, 0, 0, 0)
        info_grid.setHorizontalSpacing(12)  # Augmenté de 10 à 12
        info_grid.setVerticalSpacing(6)     # Augmenté de 4 à 6
        
        self.pot   = L()
        self.tocall= L()
        self.stack = L()
        self.dealer= L()
        self.players_count = L()
        self.blinds = L()
        info_grid.addWidget(self.pot,   0, 0)
        info_grid.addWidget(self.tocall,0, 1)
        info_grid.addWidget(self.stack, 1, 0)
        info_grid.addWidget(self.dealer,1, 1)
        info_grid.addWidget(self.players_count, 2, 0)
        info_grid.addWidget(self.blinds,2, 1)

        # Action principale
        self.action = L(font_x)
        self.action.setAlignment(QtCore.Qt.AlignCenter)

        # Barre de confiance
        self.confbar = QtWidgets.QProgressBar()
        self.confbar.setTextVisible(False)
        self.confbar.setRange(0, 100)
        self.confbar.setFixedHeight(10)  # Augmenté de 8 à 10
        self.confbar.setStyleSheet(
            "QProgressBar{background: rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.18); border-radius:4px;}"
            "QProgressBar::chunk{background: rgba(255,255,255,0.55); border-radius:4px;}"
        )

        # Indicateur de chargement (indéterminé)
        self.loader = QtWidgets.QProgressBar()
        self.loader.setRange(0,0)
        self.loader.setFixedHeight(8)  # Augmenté de 6 à 8
        self.loader.setTextVisible(False)
        self.loader.setVisible(False)
        self.loader.setStyleSheet(
            "QProgressBar{background: rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.14); border-radius:4px;}"
            "QProgressBar::chunk{background: rgba(255,255,255,0.65); border-radius:4px;}"
        )

        # Layout principal
        lay.addLayout(status_layout)
        lay.addWidget(self.mode_lbl)
        lay.addWidget(self.loader)
        lay.addSpacing(4)  # Espacement supplémentaire
        lay.addWidget(self.hero)
        lay.addWidget(self.board)
        lay.addSpacing(4)  # Espacement supplémentaire
        lay.addLayout(info_grid)
        lay.addStretch(1)
        lay.addWidget(self.action)
        lay.addSpacing(4)  # Espacement supplémentaire
        lay.addWidget(self.confbar)
        lay.addWidget(self.perf_lbl)

        self.panel = panel
        self._panel_bg_style = self.panel.styleSheet()

        # Titlebar (drag/close) visible seulement en mode interaction
        self._setup_titlebar()

        # Hotkeys avec explications
        self._setup_hotkeys()

        # État
        self.paused = False
        self.busy   = False
        self.last_policy_ts = 0.0
        self.last_sig = ""
        self.force_policy_once = False
        self.auto_mode = True
        self.show_rois = False
        self.detailed_mode = False
        self._debug_rois = []
        self._last_table_rect = None
        self._policy_cache = {}

        # Timer principal OU mode on-demand
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        if not ON_DEMAND:
            self.timer.start(REFRESH_MS)
        else:
            self.mode_lbl.setText("Veille — appuie sur Espace")
            QtCore.QTimer.singleShot(80, self._warmup)

        # Animation de pulse pour le loader
        self.pulse_animation = QtCore.QPropertyAnimation(self.loader, b"value")
        self.pulse_animation.setStartValue(0)
        self.pulse_animation.setEndValue(100)
        self.pulse_animation.setDuration(1000)
        self.pulse_animation.setLoopCount(-1)  # Infinite loop

        # Définir le statut initial
        self.set_status("normal", "Prêt")

    def _setup_hotkeys(self):
        """Configure tous les raccourcis clavier avec leurs explications"""
        # Liste des raccourcis avec descriptions
        self.hotkeys = {
            "Space": "Lancer OCR + IA (une passe)",
            "Shift+Space": "Lancer OCR seul",
            "F4": "Basculer mode interaction (drag/click)",
            "F5": "Afficher/masquer ROIs debug",
            "F6": "Cycle fenêtre",
            "F7": "Lock/Unlock fenêtre",
            "F8": "Cacher/Afficher le HUD",
            "F9": "Pause/Reprise (si timer actif)",
            "F10": "Forcer une requête policy immédiate",
            "F11": "Basculer AUTO/MANUEL (policy)",
            "F3": "Basculer mode détaillé",
            "F12/Esc": "Fermer l'application"
        }
        
        # Configurer les raccourcis
        QtGui.QShortcut(QtGui.QKeySequence("F8"), self, activated=self.toggle_visible)
        QtGui.QShortcut(QtGui.QKeySequence("F9"), self, activated=self.toggle_pause)
        QtGui.QShortcut(QtGui.QKeySequence("F10"), self, activated=self.ask_now)
        QtGui.QShortcut(QtGui.QKeySequence("F11"), self, activated=self.toggle_mode)
        QtGui.QShortcut(QtGui.QKeySequence("F5"), self, activated=self.toggle_rois)
        QtGui.QShortcut(QtGui.QKeySequence("F4"), self, activated=self.toggle_interact)
        QtGui.QShortcut(QtGui.QKeySequence("F3"), self, activated=self.toggle_detailed_mode)
        QtGui.QShortcut(QtGui.QKeySequence("F12"), self, activated=self.close)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, activated=self.close)
        QtGui.QShortcut(QtGui.QKeySequence("Space"), self, activated=self.run_once)
        QtGui.QShortcut(QtGui.QKeySequence("Shift+Space"), self, activated=self.run_once_ocr_only)
        QtGui.QShortcut(QtGui.QKeySequence("F6"), self, activated=self.on_cycle_window)
        QtGui.QShortcut(QtGui.QKeySequence("F7"), self, activated=self.on_toggle_lock)

    # ----- Lock/Windows -----
    @QtCore.Slot()
    def on_cycle_window(self):
        """Cycle entre les fenêtres disponibles"""
        LOCK.cycle()
        self.set_status("normal", "Cyclage des fenêtres")

    @QtCore.Slot()
    def on_toggle_lock(self):
        """Verrouille/Déverrouille la fenêtre actuelle"""
        LOCK.toggle_lock()
        status = "verrouillée" if LOCK.get_status().locked else "déverrouillée"
        self.set_status("normal", f"Fenêtre {status}")

    # ----- UI dynamics -----
    def _refresh_mode_label(self):
        self.mode_lbl.setText("Mode: " + ("AUTO" if self.auto_mode else "MANUEL"))

    def set_status(self, status, message=""):
        status_colors = {
            "normal": "#16a34a",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "processing": "#3b82f6"
        }
        
        color = status_colors.get(status, "#9ca3af")
        self.status_indicator.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
        self.status_message.setText(message)

    @QtCore.Slot()
    def toggle_visible(self):
        """Afficher ou masquer le HUD"""
        self.setVisible(not self.isVisible())
        status = "masqué" if not self.isVisible() else "affiché"
        self.set_status("normal", f"HUD {status}")

    @QtCore.Slot()
    def toggle_pause(self):
        """Mettre en pause ou reprendre l'analyse"""
        self.paused = not self.paused
        self.mode_lbl.setText(("⏸ Pause — " if self.paused else "") + ("AUTO" if self.auto_mode else "MANUEL"))
        self.set_status("warning" if self.paused else "normal", "En pause" if self.paused else "Actif")

    @QtCore.Slot()
    def ask_now(self):
        """Forcer une analyse immédiate"""
        self.force_policy_once = True
        self.mode_lbl.setText("⏳ Demande de conseil…")
        self.set_status("processing", "Analyse en cours...")

    @QtCore.Slot()
    def toggle_mode(self):
        """Basculer entre mode AUTO et MANUEL"""
        self.auto_mode = not self.auto_mode
        self._refresh_mode_label()
        self.set_status("normal", "Mode " + ("AUTO" if self.auto_mode else "MANUEL"))

    @QtCore.Slot()
    def toggle_rois(self):
        """Afficher ou masquer les ROIs de débogage"""
        self.show_rois = not self.show_rois
        if not self.show_rois:
            self._debug_rois = []
        self.update()
        self.set_status("normal", "Debug ROIs " + ("activé" if self.show_rois else "désactivé"))

    @QtCore.Slot()
    def toggle_detailed_mode(self):
        """Basculer entre mode compact et détaillé"""
        self.detailed_mode = not self.detailed_mode
        if self.detailed_mode:
            self.setFixedSize(BOX_SIZE, BOX_SIZE + 80)
            self.set_status("normal", "Mode détaillé activé")
        else:
            self.setFixedSize(BOX_SIZE, BOX_SIZE)
            self.set_status("normal", "Mode compact activé")
        self._setup_titlebar()  # Recalculer la position de la titlebar

    # ----- Loop principal -----
    @QtCore.Slot()
    def tick(self):
        if self.paused or self.busy:
            return
        self._run_worker(allow_auto=True, force_policy=False)

    def run_once(self):
        """Lancer une analyse OCR + IA"""
        if self.busy:
            return
        self._show_loading(True)
        self._run_worker(allow_auto=False, force_policy=True)

    def run_once_ocr_only(self):
        """Lancer une analyse OCR seulement"""
        if self.busy:
            return
        self._show_loading(True)
        self._run_worker(allow_auto=False, force_policy=False)

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
            want_debug_rois=self.show_rois,
            player_logger=self.player_logger
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
        self._show_loading(False)
        if res.table_rect:
            self._last_table_rect = res.table_rect
            self._maybe_follow_roi(res.table_rect)

        self.hero.setText("Hero: " + (" ".join(res.hero) if res.hero else "—"))
        self.board.setText("Board: " + (" ".join(res.board) if res.board else "—"))
        self.pot.setText(f"Pot: {res.pot:.2f} €")
        self.tocall.setText(f"À suivre: {res.to_call:.2f} €")
        self.stack.setText(f"Stack: {res.stack:.2f} €")
        self.dealer.setText(f"BTN: {res.dealer if res.dealer is not None else '—'}")
        self.players_count.setText(f"Joueurs: {res.players_count}")
        self.blinds.setText(f"Blinds: {res.blinds[0]}/{res.blinds[1]}")

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

            icon = PALETTE.get(typ, {}).get("icon", "?")
            txt = f"{icon} {typ.upper()}"
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

        self.set_status("normal", "Analyse terminée")

    @QtCore.Slot(str)
    def on_error(self, msg: str):
        self._show_loading(False)
        self.perf_lbl.setText(f"ERR: {msg}")
        self.set_status("error", msg)

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

    def _show_loading(self, flag: bool):
        self.loader.setVisible(flag)
        if flag:
            self.mode_lbl.setText("⏳ Lecture en cours…")
            self.pulse_animation.start()
            self.set_status("processing", "Analyse en cours...")
        else:
            self._refresh_mode_label()
            self.pulse_animation.stop()
            self.loader.setValue(0)

    # ----- titlebar/interaction -----
    def _setup_titlebar(self):
        self.titlebar = QtWidgets.QFrame(self)
        self.titlebar.setObjectName("titlebar")
        self.titlebar.setFixedHeight(28)
        self.titlebar.setStyleSheet(
            f"QFrame#titlebar{{background: rgba({theme['bg']},0.8); border-radius: 8px;}}"
            f"QLabel{{color:{theme['text']}; font-size:12px; padding-left:8px;}}"
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
        self.set_status("normal", "Mode interactif " + ("activé" if self.interact_mode else "désactivé"))

    # ----- debug/warmup & géométrie -----
    def _warmup(self):
        try:
            eng = get_engine()
            if hasattr(eng, "warmup"):
                eng.warmup()
        except Exception:
            pass

    def _place_default(self):
        screen_geo = QtGui.QGuiApplication.primaryScreen().geometry()
        self.move(screen_geo.left()+20, screen_geo.top()+20)

    def auto_position(self):
        if not self._last_table_rect:
            return
            
        x, y, w, h = self._last_table_rect
        screen_geo = QtGui.QGuiApplication.primaryScreen().geometry()
        
        # Essayer différentes positions autour de la table
        positions = [
            (x + w + 10, y + 10),      # Droite
            (x - BOX_SIZE - 10, y + 10), # Gauche
            (x + 10, y - BOX_SIZE - 10), # Haut
            (x + 10, y + h + 10)        # Bas
        ]
        
        # Choisir la position qui ne chevauche pas la table
        for pos in positions:
            if (0 <= pos[0] <= screen_geo.width() - BOX_SIZE and 
                0 <= pos[1] <= screen_geo.height() - BOX_SIZE):
                self.move(pos[0], pos[1])
                break

    def _maybe_follow_roi(self, table_rect):
        if not FOLLOW_ROI or not table_rect:
            return
        try:
            x, y, w, h = table_rect
            dx, dy = BOX_OFFSET
            self.move(x + dx, y + dy)
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
            qp.drawRect(int(x), int(y), int(w), int(h))
            qp.drawText(int(x)+3, int(y)+14, str(label))
        qp.end()

# ---------- Entrée ----------
def run():
    # Essayer sans l'attribut UseSoftwareOpenGL
    # if os.getenv("POKERIA_USE_SOFTGL", "1") == "1":
    #     QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseSoftwareOpenGL, True)
    
    app = QtWidgets.QApplication([])
    
    # Cette ligne causait l'erreur - AA_UseStyleSheets n'existe pas dans PySide6
    # app.setAttribute(QtCore.Qt.AA_UseStyleSheets, True)
    
    try:
        LOCK.refresh()
    except Exception:
        pass
    
    w = CompactOverlay()
    
    # Essayer une approche différente pour afficher la fenêtre
    try:
        w.show()
    except Exception as e:
        print(f"Erreur lors de l'affichage: {e}")
        # Essayer une autre méthode
        w.setVisible(True)
    
    app.exec()

if __name__ == "__main__":
    run()