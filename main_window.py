#!/usr/bin/env python3
"""
main_window.py

Finestra principale con pannello tools e chat AI switchabili.
"""

import os
import json
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QSplitter, QFrame, QListWidgetItem,
    QLineEdit, QSpinBox, QComboBox, QMessageBox, QScrollArea,
    QStackedWidget, QTextEdit, QListWidget
)
from PySide6.QtCore import Qt, QUrl, QThreadPool, QTimer, Slot, QSettings
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QKeyEvent

from config import AppConfig, DARK_THEME_QSS
from models import MediaItem, TimelineClip
from widgets import MediaListWidget
from graphics import VisualTimeline, ClipGraphicsItem
from preview_worker import PreviewWorker
from effect_preview_worker import EffectPreviewWorker
from utils import ensure_dir
from export import ProjectExporter


class ChatMessage(QWidget):
    """Widget per un singolo messaggio nella chat."""
    
    def __init__(self, text: str, is_user: bool = True, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        
        # Bubble del messaggio
        bubble = QFrame()
        bubble.setObjectName("chatBubble")
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        
        # Testo del messaggio
        msg_label = QLabel(text)
        msg_label.setWordWrap(True)
        msg_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        # Timestamp
        time_label = QLabel(datetime.now().strftime("%H:%M"))
        time_label.setObjectName("timestamp")
        
        bubble_layout.addWidget(msg_label)
        bubble_layout.addWidget(time_label, alignment=Qt.AlignRight)
        
        # Stile diverso per user e bot
        if is_user:
            bubble.setProperty("userMessage", True)
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            bubble.setProperty("botMessage", True)
            layout.addWidget(bubble)
            layout.addStretch()


class MainWindow(QMainWindow):
    """Finestra principale dell'applicazione."""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle(AppConfig.WINDOW_TITLE)
        self.resize(AppConfig.WINDOW_WIDTH, AppConfig.WINDOW_HEIGHT)
        
        # Data
        self.media_items: List[MediaItem] = []
        self.timeline: List[TimelineClip] = []
        self.project_bg_music: Optional[str] = None
        
        # Chat history
        self.chat_history: List[dict] = []
        
        # Directories
        self.lut_dir = os.path.join(os.path.dirname(__file__), "luts")
        os.makedirs(self.lut_dir, exist_ok=True)
        
        self._temp_preview_root = ensure_dir(
            os.path.join(
                tempfile.gettempdir(), 
                f"pyeditor_previews_{uuid.uuid4().hex}"
            )
        )
        
        # Threading
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(AppConfig.MAX_PREVIEW_THREADS)
        
        # Cache
        self._wave_cache = {}
        self._thumbs_cache = {}
        self._proxy_cache = {}
        
        # Seek throttling
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(AppConfig.SEEK_THROTTLE_MS)
        self._seek_timer.timeout.connect(self._do_seek_pending)
        self._pending_seek_ms = 0
        
        # Build UI
        self._build_ui()
        self.setStyleSheet(DARK_THEME_QSS)
        self._connect_signals()
    
    def _build_ui(self):
        """Costruisce l'interfaccia utente."""
        # Toolbar
        toolbar = self._create_toolbar()
        
        # Left panel: Media Library
        left_panel = self._create_media_library_panel()
        
        # Center panel: Preview + Timeline
        center_panel = self._create_center_panel()
        
        # Right panel: Switchable (Tools / Chat)
        right_panel = self._create_right_panel()
        
        # Assembly
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        
        center_widget = QWidget()
        center_widget.setLayout(center_panel)
        
        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 2)
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(toolbar)
        main_layout.addWidget(splitter)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
    
    def _create_toolbar(self) -> QFrame:
        """Crea la toolbar."""
        toolbar = QFrame(self)
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(60)
        
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 8, 10, 8)

        # Left group
        left = QHBoxLayout()
        self.btn_import = QPushButton("Import")
        self.btn_import.setProperty("primary", True)
        self.btn_import.clicked.connect(self.import_media)

        self.btn_add_to_tl = QPushButton("Add")
        self.btn_add_to_tl.setProperty("secondary", True)
        self.btn_add_to_tl.clicked.connect(self.add_selected_to_timeline)

        self.track_selector = QComboBox()
        self.track_selector.addItems(["Track 1", "Track 2"])
        self.track_selector.setFixedWidth(100)

        left.addWidget(self.btn_import)
        left.addWidget(self.btn_add_to_tl)
        left.addWidget(self.track_selector)

        # Center group
        center = QHBoxLayout()
        center.addStretch()
        center.addWidget(QLabel("Timeline"))
        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.clicked.connect(self.fit_timeline)

        center.addSpacing(8)
        center.addWidget(self.btn_zoom_out)
        center.addWidget(self.btn_zoom_in)
        center.addWidget(self.btn_fit)
        center.addStretch()

        # Right group
        right = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save_project)
        btn_load = QPushButton("Load")
        btn_load.clicked.connect(self.load_project)
        right.addStretch()
        right.addWidget(btn_save)
        right.addWidget(btn_load)

        layout.addLayout(left)
        layout.addLayout(center)
        layout.addLayout(right)
        
        return toolbar
    
    def _create_media_library_panel(self) -> QVBoxLayout:
        """Crea il pannello della libreria media."""
        self.lib_list = MediaListWidget()
        self.lib_list.setFixedWidth(270)
        self.lib_list.setDragEnabled(True)
        self.lib_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.lib_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lib_list.itemDoubleClicked.connect(self.on_media_double)
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Media Library"))
        layout.addWidget(self.lib_list)
        
        return layout
    
    def _create_center_panel(self) -> QVBoxLayout:
        """Crea il pannello centrale."""
        # Video widget
        self.video_widget = QVideoWidget()
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.player.setVideoOutput(self.video_widget)

        # Controls
        play_btn = QPushButton("Play")
        play_btn.clicked.connect(self.toggle_play)

        pause_btn = QPushButton("Pause")
        pause_btn.clicked.connect(self.player.pause)

        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self.player.stop)

        jump_start_btn = QPushButton("<<")
        jump_start_btn.clicked.connect(self.seek_to_start_of_selected_clip)

        ctrls = QHBoxLayout()
        ctrls.addWidget(play_btn)
        ctrls.addWidget(pause_btn)
        ctrls.addWidget(stop_btn)
        ctrls.addWidget(jump_start_btn)

        # Visual timeline
        self.visual_timeline = VisualTimeline()
        self.visual_timeline.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.visual_timeline.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Textual timeline list
        self.tl_list = MediaListWidget()
        self.tl_list.setFixedHeight(110)
        self.tl_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tl_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tl_list.itemClicked.connect(self.on_tl_selected)

        # Bottom widget
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addLayout(ctrls)
        bottom_layout.addWidget(QLabel("Timeline (visual)"))
        bottom_layout.addWidget(self.visual_timeline)
        bottom_layout.addWidget(QLabel("Timeline (list)"))
        bottom_layout.addWidget(self.tl_list)
        bottom_widget.setLayout(bottom_layout)

        # Splitter verticale
        splitter = QSplitter(Qt.Vertical)
        self.video_widget.setMinimumHeight(120)
        self.video_widget.setMaximumHeight(320)
        splitter.addWidget(self.video_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([180, 340])
        
        self.center_splitter = splitter
        
        try:
            self._restore_center_splitter()
        except Exception:
            pass

        layout = QVBoxLayout()
        layout.addWidget(splitter)

        return layout

    def _restore_center_splitter(self):
        """Restore center splitter sizes."""
        try:
            settings = QSettings("PyEditor", "PyEditorApp")
            val = settings.value("centerSplitterSizes", None)
            if val:
                if isinstance(val, (list, tuple)):
                    sizes = [int(x) for x in val]
                else:
                    try:
                        sizes = [int(x) for x in str(val).split(',')]
                    except Exception:
                        sizes = None

                if sizes and hasattr(self, 'center_splitter'):
                    self.center_splitter.setSizes(sizes)
        except Exception:
            pass

    def _save_center_splitter(self):
        """Save center splitter sizes."""
        try:
            if hasattr(self, 'center_splitter'):
                sizes = self.center_splitter.sizes()
                settings = QSettings("PyEditor", "PyEditorApp")
                settings.setValue("centerSplitterSizes", sizes)
        except Exception:
            pass

    def closeEvent(self, event):
        """Persist UI state."""
        try:
            self._save_center_splitter()
        except Exception:
            pass
        super().closeEvent(event)
    
    def _create_right_panel(self) -> QWidget:
        """Crea il pannello destro switchabile (Tools / Chat)."""
        container = QWidget()
        container.setObjectName("rightPanel")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header con switch buttons
        header = QFrame()
        header.setObjectName("rightPanelHeader")
        header.setFixedHeight(50)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 8, 8, 8)
        
        self.btn_tools = QPushButton("🛠 Tools")
        self.btn_tools.setCheckable(True)
        self.btn_tools.setChecked(True)
        self.btn_tools.setProperty("panelSwitch", True)
        self.btn_tools.clicked.connect(lambda: self._switch_right_panel(0))
        
        self.btn_chat = QPushButton("💬 AI Chat")
        self.btn_chat.setCheckable(True)
        self.btn_chat.setProperty("panelSwitch", True)
        self.btn_chat.clicked.connect(lambda: self._switch_right_panel(1))
        
        header_layout.addWidget(self.btn_tools)
        header_layout.addWidget(self.btn_chat)
        
        # Stacked widget per i due pannelli
        self.right_stack = QStackedWidget()
        
        # Pannello 1: Tools (scroll area)
        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tools_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        tools_widget = QWidget()
        tools_widget.setObjectName("toolsPanel")
        tools_layout = self._create_tools_panel()
        tools_widget.setLayout(tools_layout)
        
        tools_scroll.setWidget(tools_widget)
        
        # Pannello 2: Chat (scroll area)
        chat_scroll = QScrollArea()
        chat_scroll.setWidgetResizable(True)
        chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        chat_widget = QWidget()
        chat_widget.setObjectName("chatPanel")
        chat_layout = self._create_chat_panel()
        chat_widget.setLayout(chat_layout)
        
        chat_scroll.setWidget(chat_widget)
        
        # Aggiungi i pannelli allo stack
        self.right_stack.addWidget(tools_scroll)
        self.right_stack.addWidget(chat_scroll)
        
        # Assembly
        main_layout.addWidget(header)
        main_layout.addWidget(self.right_stack)
        
        return container
    
    def _switch_right_panel(self, index: int):
        """Switch tra Tools e Chat panel."""
        self.right_stack.setCurrentIndex(index)
        
        # Aggiorna bottoni
        self.btn_tools.setChecked(index == 0)
        self.btn_chat.setChecked(index == 1)
    
    def _create_tools_panel(self) -> QVBoxLayout:
        """Crea il pannello tools."""
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        layout.addWidget(QLabel("Clip Tools"))
        
        # Trim controls
        layout.addWidget(QLabel("Start (sec)"))
        self.start_edit = QLineEdit("0.0")
        layout.addWidget(self.start_edit)
        
        layout.addWidget(QLabel("End (sec)"))
        self.end_edit = QLineEdit("")
        layout.addWidget(self.end_edit)
        
        apply_trim_btn = QPushButton("Apply Trim")
        apply_trim_btn.clicked.connect(self.apply_trim_to_clip)
        layout.addWidget(apply_trim_btn)
        layout.addSpacing(12)
        
        # Title controls
        layout.addWidget(QLabel("Title Text"))
        self.title_edit = QLineEdit("")
        layout.addWidget(self.title_edit)
        
        layout.addWidget(QLabel("Title Size"))
        self.title_size = QSpinBox()
        self.title_size.setRange(8, 200)
        self.title_size.setValue(36)
        layout.addWidget(self.title_size)
        
        apply_title_btn = QPushButton("Apply Title")
        apply_title_btn.clicked.connect(self.apply_title_to_clip)
        layout.addWidget(apply_title_btn)
        layout.addSpacing(12)

        # Speed controls
        layout.addWidget(QLabel("Speed (velocity, 0.25x–4x)"))
        from PySide6.QtWidgets import QDoubleSpinBox
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.25, 4.0)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setDecimals(2)
        layout.addWidget(self.speed_spin)

        apply_speed_btn = QPushButton("Apply Speed")
        apply_speed_btn.clicked.connect(self.apply_speed_to_clip)
        layout.addWidget(apply_speed_btn)
        layout.addSpacing(12)
        
        # LUT controls
        layout.addWidget(QLabel("Color/LUT"))
        self.lut_combo = QComboBox()
        self._refresh_lut_list()
        layout.addWidget(self.lut_combo)
        
        apply_lut_btn = QPushButton("Apply LUT to Clip")
        apply_lut_btn.clicked.connect(self.apply_lut_to_clip)
        layout.addWidget(apply_lut_btn)
        layout.addSpacing(12)

        # Preview settings
        layout.addWidget(QLabel("Preview Resolution"))
        self.preview_res_combo = QComboBox()
        self.preview_res_combo.addItems(["360p", "480p", "640p (default)", "720p"])
        self.preview_res_combo.setCurrentIndex(2)
        layout.addWidget(self.preview_res_combo)

        self.proxy_checkbox = QPushButton("Use Proxies")
        self.proxy_checkbox.setCheckable(True)
        self.proxy_checkbox.setChecked(False)
        layout.addWidget(self.proxy_checkbox)

        # Proxy management
        regen_proxy_btn = QPushButton("Regenerate Proxy")
        regen_proxy_btn.clicked.connect(self._on_regenerate_proxy_clicked)
        layout.addWidget(regen_proxy_btn)

        clear_proxy_btn = QPushButton("Clear Proxy")
        clear_proxy_btn.clicked.connect(self._on_clear_proxy_clicked)
        layout.addWidget(clear_proxy_btn)
        
        layout.addSpacing(12)
        
        # Transition controls
        layout.addWidget(QLabel("Transition to next clip"))
        self.transition_combo = QComboBox()
        # Supported xfade transitions
        self.transition_combo.addItems([
            "none",
            "crossfade",
            "fade",
            "wipeleft",
            "wiperight",
            "wipeup",
            "wipedown",
            "slideleft",
            "slideright",
            "circleopen",
            "circleclose"
        ])
        layout.addWidget(self.transition_combo)
        
        apply_transition_btn = QPushButton("Set Transition")
        apply_transition_btn.clicked.connect(self.set_transition_for_selected)
        layout.addWidget(apply_transition_btn)
        layout.addSpacing(12)
        
        # Clip operations
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_selected_clip)
        layout.addWidget(remove_btn)
        
        split_btn = QPushButton("Split at Playhead")
        split_btn.clicked.connect(self.split_at_playhead)
        layout.addWidget(split_btn)
        
        duplicate_btn = QPushButton("Duplicate Clip")
        duplicate_btn.clicked.connect(self.duplicate_selected_clip)
        layout.addWidget(duplicate_btn)
        
        layout.addSpacing(12)
        
        # Background music
        attach_music_btn = QPushButton("Choose Background Music")
        attach_music_btn.clicked.connect(self.choose_bg_music)
        layout.addWidget(attach_music_btn)
        
        self.bg_music_label = QLabel("No music")
        self.bg_music_label.setWordWrap(True)
        layout.addWidget(self.bg_music_label)
        
        layout.addSpacing(12)
        
        # Export
        export_btn = QPushButton("Export Project")
        export_btn.clicked.connect(self.export_project)
        export_btn.setProperty("primary", True)
        layout.addWidget(export_btn)
        
        # Progress indicator
        from PySide6.QtWidgets import QProgressBar
        self.preview_progress = QProgressBar()
        self.preview_progress.setMinimum(0)
        self.preview_progress.setMaximum(0)
        self.preview_progress.setVisible(False)
        layout.addWidget(self.preview_progress)

        self.preview_status_label = QLabel("")
        self.preview_status_label.setWordWrap(True)
        self.preview_status_label.setVisible(False)
        layout.addWidget(self.preview_status_label)
        
        layout.addStretch()

        return layout
    
    def _create_chat_panel(self) -> QVBoxLayout:
        """Crea il pannello chat AI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header
        header_label = QLabel("🤖 AI Assistant")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00b4d6;")
        layout.addWidget(header_label)
        
        # Info label
        info_label = QLabel("Ask me anything about video editing, effects, or timeline operations!")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: rgba(230,238,246,0.7); font-size: 8pt;")
        layout.addWidget(info_label)
        
        layout.addSpacing(8)
        
        # Chat messages area (scrollable)
        self.chat_messages_widget = QWidget()
        self.chat_messages_layout = QVBoxLayout(self.chat_messages_widget)
        self.chat_messages_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_messages_layout.setSpacing(8)
        self.chat_messages_layout.addStretch()
        
        # Scroll area for messages
        chat_scroll = QScrollArea()
        chat_scroll.setWidgetResizable(True)
        chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chat_scroll.setWidget(self.chat_messages_widget)
        chat_scroll.setMinimumHeight(300)
        
        layout.addWidget(chat_scroll, 1)
        
        # Input area
        input_frame = QFrame()
        input_frame.setObjectName("chatInputFrame")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)
        
        self.chat_input = QTextEdit()
        self.chat_input.setPlaceholderText("Type your message here...")
        self.chat_input.setMaximumHeight(80)
        self.chat_input.setMinimumHeight(60)
        
        # Bottoni azione
        buttons_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Clear Chat")
        clear_btn.clicked.connect(self._clear_chat)
        
        send_btn = QPushButton("Send")
        send_btn.setProperty("primary", True)
        send_btn.clicked.connect(self._send_chat_message)
        
        buttons_layout.addWidget(clear_btn)
        buttons_layout.addStretch()
        buttons_layout.addWidget(send_btn)
        
        input_layout.addWidget(self.chat_input)
        input_layout.addLayout(buttons_layout)
        
        layout.addWidget(input_frame)
        
        # Messaggio di benvenuto
        self._add_chat_message("Hello! I'm your AI video editing assistant. How can I help you today?", is_user=False)
        
        return layout
    
    def _send_chat_message(self):
        """Invia un messaggio nella chat."""
        text = self.chat_input.toPlainText().strip()
        
        if not text:
            return
        
        # Aggiungi messaggio utente
        self._add_chat_message(text, is_user=True)
        
        # Salva nella history
        self.chat_history.append({"role": "user", "content": text})
        
        # Pulisci input
        self.chat_input.clear()
        
        # Simula risposta bot (qui puoi integrare una vera AI)
        QTimer.singleShot(500, lambda: self._bot_response(text))
    
    def _bot_response(self, user_message: str):
        """Genera una risposta del bot."""
        # Risposte predefinite (sostituisci con vera AI)
        responses = {
            "help": "I can help you with:\n• Trim and split clips\n• Apply effects and LUTs\n• Add titles and transitions\n• Export your project\n\nWhat would you like to do?",
            "trim": "To trim a clip:\n1. Select the clip in timeline\n2. Go to Tools panel\n3. Set Start and End times\n4. Click 'Apply Trim'",
            "export": "To export your project:\n1. Make sure all clips are in timeline\n2. Optional: Add background music\n3. Click 'Export Project' in Tools\n4. Choose output location",
            "lut": "LUTs (Look-Up Tables) apply color grading:\n1. Select a clip\n2. Choose a LUT from dropdown\n3. Click 'Apply LUT to Clip'\n\nPlace .cube files in the 'luts' folder!",
            "transition": "To add transitions:\n1. Select a clip\n2. Choose transition type (none/crossfade)\n3. Click 'Set Transition'\n\nThis will transition into the next clip!",
        }
        
        # Cerca keyword nella domanda
        response = "I'm here to help! Try asking about: trim, export, LUT, transition, or type 'help' for more options."
        
        for keyword, answer in responses.items():
            if keyword in user_message.lower():
                response = answer
                break
        
        # Aggiungi risposta bot
        self._add_chat_message(response, is_user=False)
        
        # Salva nella history
        self.chat_history.append({"role": "assistant", "content": response})
    
    def _add_chat_message(self, text: str, is_user: bool = True):
        """Aggiunge un messaggio alla chat."""
        # Rimuovi stretch temporaneamente
        if self.chat_messages_layout.count() > 0:
            item = self.chat_messages_layout.takeAt(self.chat_messages_layout.count() - 1)
            if item.spacerItem():
                del item
        
        # Aggiungi nuovo messaggio
        message = ChatMessage(text, is_user)
        self.chat_messages_layout.addWidget(message)
        
        # Ri-aggiungi stretch
        self.chat_messages_layout.addStretch()
        
        # Scroll to bottom
        QTimer.singleShot(100, self._scroll_chat_to_bottom)
    
    def _scroll_chat_to_bottom(self):
        """Scrolla la chat fino in fondo."""
        scroll_area = self.chat_messages_widget.parent()
        if isinstance(scroll_area, QScrollArea):
            scrollbar = scroll_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def _clear_chat(self):
        """Pulisce la chat."""
        # Rimuovi tutti i messaggi
        while self.chat_messages_layout.count() > 1:  # Lascia lo stretch
            item = self.chat_messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Reset history
        self.chat_history.clear()
        
        # Messaggio di benvenuto
        self._add_chat_message("Chat cleared! How can I assist you?", is_user=False)
    
    def _connect_signals(self):
        """Connette i segnali."""
        self.visual_timeline.orderChanged.connect(self._on_visual_order_changed)
        self.visual_timeline.clipSelected.connect(self._on_visual_clip_selected)
        self.visual_timeline.trimChanged.connect(self._on_visual_trim_changed)
        self.visual_timeline.scrubbed.connect(self._on_scrubbed)
        self.player.positionChanged.connect(self._on_player_position_changed)
    
    # --- Keyboard Shortcuts ---
    
    def keyPressEvent(self, event: QKeyEvent):
        """Gestisce gli shortcut da tastiera."""
        key = event.key()
        
        # Se siamo nella chat e premiamo Enter, invia messaggio
        if self.chat_input.hasFocus():
            if key == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
                self._send_chat_message()
                event.accept()
                return
        
        if key == Qt.Key_T:
            self.split_at_playhead()
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.remove_selected_clip()
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
        elif key == Qt.Key_Minus:
            self.zoom_out()
        elif key == Qt.Key_F:
            self.fit_timeline()
        elif key == Qt.Key_Space:
            self.toggle_play()
        else:
            super().keyPressEvent(event)
    
    # --- Media Library Actions ---
    
    def import_media(self):
        """Importa file media nella libreria."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Import media", 
            str(Path.home()),
            "Media files (*.mp4 *.mov *.mkv *.avi *.mp3 *.wav *.png *.jpg *.jpeg)"
        )
        
        for path in paths:
            self._add_media_to_library(path)
    
    def _add_media_to_library(self, path: str):
        """Aggiunge un media alla libreria."""
        media_item = MediaItem(path)
        self.media_items.append(media_item)
        
        duration_str = f" ({media_item.duration:.2f}s)" if media_item.duration else ""
        item_text = f"{media_item.name} [{media_item.type}]{duration_str}"
        
        list_item = QListWidgetItem(item_text)
        list_item.setData(Qt.UserRole, media_item)
        self.lib_list.addItem(list_item)
    
    def on_media_double(self, item: QListWidgetItem):
        """Gestisce il doppio click su un media nella libreria."""
        media_item = item.data(Qt.UserRole)
        
        if media_item.type in ("video", "audio"):
            self.player.setSource(QUrl.fromLocalFile(media_item.path))
            self.player.play()
    
    # --- Timeline Actions ---
    
    def add_selected_to_timeline(self):
        """Aggiunge il media selezionato alla timeline."""
        sel = self.lib_list.currentItem()
        
        if not sel:
            QMessageBox.information(
                self, 
                "Select media", 
                "Select an item in the Media Library first."
            )
            return
        
        media_item = sel.data(Qt.UserRole)
        self._append_media_path_to_timeline(media_item.path)
    
    def drop_media_on_timeline(self, path: str):
        """Gestisce il drop di un media sulla timeline."""
        if not any(m.path == path for m in self.media_items):
            self._add_media_to_library(path)
        
        self._append_media_path_to_timeline(path)
    
    def _append_media_path_to_timeline(self, path: str):
        """Aggiunge un media alla timeline dato il percorso."""
        media_item = next((m for m in self.media_items if m.path == path), None)
        
        if not media_item:
            media_item = MediaItem(path)
            self.media_items.append(media_item)
        
        clip = TimelineClip(media_item)
        self._prepare_clip_previews(clip)
        
        try:
            clip.track = int(self.track_selector.currentIndex())
        except Exception:
            clip.track = 0

        self.timeline.append(clip)
        
        list_item = QListWidgetItem(f"{media_item.name}  [{media_item.type}]")
        list_item.setData(Qt.UserRole, clip)
        self.tl_list.addItem(list_item)
        
        self.visual_timeline.append_clip(clip)
    
    def _on_visual_order_changed(self, new_order_clips: List[TimelineClip]):
        """Gestisce il cambio d'ordine dei clip."""
        self.timeline = list(new_order_clips)
        
        self.tl_list.clear()
        for clip in self.timeline:
            list_item = QListWidgetItem(f"{clip.media.name}  [{clip.media.type}]")
            list_item.setData(Qt.UserRole, clip)
            self.tl_list.addItem(list_item)
    
    def _on_visual_clip_selected(self, clip: TimelineClip):
        """Gestisce la selezione di un clip."""
        self._load_clip_into_tools(clip)
        
        if clip.media.type in ("video", "audio"):
            # Prefer an effect preview if available, otherwise proxy or original
            src_path = getattr(clip, 'effect_preview_path', None)
            if not src_path:
                src_path = clip.media.path
                if getattr(self, 'proxy_checkbox', None) and self.proxy_checkbox.isChecked():
                    if getattr(clip, 'proxy_path', None) and clip.proxy_path and os.path.exists(clip.proxy_path):
                        src_path = clip.proxy_path

            self.player.setSource(QUrl.fromLocalFile(src_path))
            try:
                # If using baked preview, keep playback at 1x; otherwise reflect speed
                spd = float(getattr(clip, 'speed', 1.0) or 1.0)
                self.player.setPlaybackRate(1.0 if getattr(clip, 'effect_preview_path', None) else (spd if spd > 0 else 1.0))
            except Exception:
                pass
            self.player.play()
        
        for i in range(self.tl_list.count()):
            item = self.tl_list.item(i)
            if item.data(Qt.UserRole) is clip:
                self.tl_list.setCurrentRow(i)
                break
    
    def _on_visual_trim_changed(self, clip: TimelineClip):
        """Aggiorna i campi di trim."""
        self.start_edit.setText(str(round(clip.start, 3)))
        self.end_edit.setText("" if clip.end is None else str(round(clip.end, 3)))
    
    def on_tl_selected(self, item: QListWidgetItem):
        """Gestisce la selezione nella lista testuale."""
        clip = item.data(Qt.UserRole)
        self._load_clip_into_tools(clip)
        
        if clip.media.type in ("video", "audio"):
            src_path = clip.media.path
            if getattr(self, 'proxy_checkbox', None) and self.proxy_checkbox.isChecked():
                if getattr(clip, 'proxy_path', None) and clip.proxy_path and os.path.exists(clip.proxy_path):
                    src_path = clip.proxy_path

            self.player.setSource(QUrl.fromLocalFile(src_path))
            self.player.play()
        
        for visual_item in self.visual_timeline.items_list:
            visual_item.setSelected(visual_item.clip is clip)
            if visual_item.clip is clip:
                self.visual_timeline.centerOn(visual_item)
    
    def _load_clip_into_tools(self, clip: TimelineClip):
        """Carica i parametri di un clip nei tool."""
        self.start_edit.setText(str(clip.start))
        self.end_edit.setText("" if clip.end is None else str(clip.end))
        self.title_edit.setText(clip.title)
        self.title_size.setValue(clip.title_size)
        # Speed
        if hasattr(self, 'speed_spin'):
            try:
                self.speed_spin.setValue(float(getattr(clip, 'speed', 1.0) or 1.0))
            except Exception:
                self.speed_spin.setValue(1.0)
    
    # --- Playback & Scrubbing ---
    
    def toggle_play(self):
        """Toggle play/pause."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    
    def seek_to_start_of_selected_clip(self):
        """Salta all'inizio del clip selezionato."""
        sel = self.tl_list.currentItem()
        
        if sel:
            clip = sel.data(Qt.UserRole)
        else:
            sel_items = [it for it in self.visual_timeline.items_list if it.isSelected()]
            if not sel_items:
                return
            clip = sel_items[0].clip
        
        self.player.setPosition(int(float(clip.start) * 1000))
        self.visual_timeline.set_playhead_seconds(self._cumulative_start_of(clip))
    
    def _on_scrubbed(self, seconds: float):
        """Gestisce lo scrubbing del playhead."""
        target = self._clip_at_global_time(seconds)
        if not target:
            return
        
        clip, local_sec = target
        # Account for speed: local timeline seconds map to media seconds * speed
        spd = float(getattr(clip, 'speed', 1.0) or 1.0)
        media_local = local_sec * (spd if spd > 0 else 1.0)
        
        for item in self.visual_timeline.items_list:
            item.setSelected(item.clip is clip)
        
        if clip.media.type in ("video", "audio"):
            # Prefer effect preview if exists; otherwise proxy/original
            desired = getattr(clip, 'effect_preview_path', None) or clip.media.path
            if not getattr(clip, 'effect_preview_path', None):
                if getattr(self, 'proxy_checkbox', None) and self.proxy_checkbox.isChecked():
                    if getattr(clip, 'proxy_path', None) and clip.proxy_path and os.path.exists(clip.proxy_path):
                        desired = clip.proxy_path

            if self.player.source().toLocalFile() != desired:
                self.player.setSource(QUrl.fromLocalFile(desired))
            
            self._pending_seek_ms = max(0, int((clip.start + media_local) * 1000))
            self._seek_timer.start()
            # Adjust playback rate if we're not using baked preview
            try:
                if getattr(clip, 'effect_preview_path', None):
                    self.player.setPlaybackRate(1.0)
                else:
                    self.player.setPlaybackRate(spd if spd > 0 else 1.0)
            except Exception:
                pass
    
    def _do_seek_pending(self):
        """Esegue il seek pendente."""
        self.player.setPosition(self._pending_seek_ms)
    
    def _on_player_position_changed(self, ms: int):
        """Sincronizza il playhead con il player."""
        sel_items = [it for it in self.visual_timeline.items_list if it.isSelected()]
        if not sel_items:
            return
        
        clip = sel_items[0].clip
        spd = float(getattr(clip, 'speed', 1.0) or 1.0)
        media_sec = (ms / 1000.0) - (clip.start or 0.0)
        local_sec = max(0.0, media_sec / (spd if spd > 0 else 1.0))
        
        global_sec = self._cumulative_start_of(clip) + local_sec
        self.visual_timeline.set_playhead_seconds(global_sec)
    
    def _clip_at_global_time(self, sec: float):
        """Trova il clip alla posizione temporale globale."""
        t = 0.0
        for item in self.visual_timeline.items_list:
            clip = item.clip
            duration = clip.duration_effective()
            
            if sec < t + duration:
                return clip, sec - t
            
            t += duration
        
        return None
    
    def _cumulative_start_of(self, clip: TimelineClip) -> float:
        """Calcola il tempo di inizio cumulativo."""
        t = 0.0
        for item in self.visual_timeline.items_list:
            if item.clip is clip:
                return t
            t += item.clip.duration_effective()
        return 0.0
    
    # --- Clip Operations ---
    
    def remove_selected_clip(self):
        """Rimuove il clip selezionato."""
        target_clip = None
        
        sel = self.tl_list.currentItem()
        if sel:
            target_clip = sel.data(Qt.UserRole)
        else:
            sel_items = [it for it in self.visual_timeline.items_list if it.isSelected()]
            if sel_items:
                target_clip = sel_items[0].clip
        
        if not target_clip:
            return
        
        self.timeline = [c for c in self.timeline if c is not target_clip]

        try:
            self.visual_timeline.ripple_delete(target_clip)
        except Exception:
            to_remove = [it for it in self.visual_timeline.items_list if it.clip is target_clip]
            for it in to_remove:
                try:
                    if it.scene() is not None:
                        self.visual_timeline.scene().removeItem(it)
                except Exception:
                    pass

            self.visual_timeline.items_list = [
                it for it in self.visual_timeline.items_list
                if it.clip is not target_clip
            ]
            self.visual_timeline.repack_by_order()

        self.tl_list.clear()
        for clip in self.timeline:
            list_item = QListWidgetItem(f"{clip.media.name}  [{clip.media.type}]")
            list_item.setData(Qt.UserRole, clip)
            self.tl_list.addItem(list_item)

    def duplicate_selected_clip(self):
        """Duplica il clip selezionato."""
        clip = self._current_clip()
        if not clip:
            return

        new_clip = TimelineClip(clip.media)
        new_clip.start = clip.start
        new_clip.end = clip.end
        new_clip.title = clip.title
        new_clip.title_size = clip.title_size
        new_clip.lut = clip.lut
        new_clip.transition = clip.transition
        try:
            new_clip.speed = float(getattr(clip, 'speed', 1.0) or 1.0)
        except Exception:
            new_clip.speed = 1.0

        self._prepare_clip_previews(new_clip)

        idx = self.timeline.index(clip)
        self.timeline.insert(idx + 1, new_clip)

        item = ClipGraphicsItem(new_clip, self.visual_timeline.px_per_sec, self._on_visual_trim_changed)
        self.visual_timeline.items_list.insert(idx + 1, item)
        self.visual_timeline.scene().addItem(item)
        self.visual_timeline.repack_by_order()

        self.tl_list.clear()
        for c in self.timeline:
            li = QListWidgetItem(f"{c.media.name}  [{c.media.type}]")
            li.setData(Qt.UserRole, c)
            self.tl_list.addItem(li)

    def show_clip_properties(self):
        """Mostra proprietà del clip."""
        clip = self._current_clip()
        if not clip:
            QMessageBox.information(self, "Select clip", "Select a clip first.")
            return

        info = (
            f"Media: {clip.media.name}\n"
            f"Type: {clip.media.type}\n"
            f"Start: {clip.start}\n"
            f"End: {clip.end if clip.end is not None else 'None'}\n"
            f"Title: {clip.title}\n"
            f"LUT: {clip.lut}\n"
            f"Transition: {clip.transition}\n"
        )

        QMessageBox.information(self, "Clip Properties", info)
    
    def split_at_playhead(self):
        """Divide il clip al playhead."""
        gsec = self.visual_timeline.playhead_sec
        target = self._clip_at_global_time(gsec)
        
        if not target:
            return
        
        clip, local_sec = target
        
        if local_sec <= 0.05 or local_sec >= clip.duration_effective() - 0.05:
            return
        
        split_abs = clip.start + local_sec
        
        left = TimelineClip(clip.media)
        left.start = clip.start
        left.end = split_abs
        left.title = clip.title
        left.title_size = clip.title_size
        left.lut = clip.lut
        left.transition = "none"
        
        right = TimelineClip(clip.media)
        right.start = split_abs
        right.end = clip.end
        right.title = clip.title
        right.title_size = clip.title_size
        right.lut = clip.lut
        right.transition = clip.transition
        
        self._prepare_clip_previews(left)
        self._prepare_clip_previews(right)
        
        idx = self.timeline.index(clip)
        self.timeline.pop(idx)
        self.timeline[idx:idx] = [left, right]
        
        new_items = []
        for item in self.visual_timeline.items_list:
            if item.clip is clip:
                self.visual_timeline.scene().removeItem(item)
                
                item_left = ClipGraphicsItem(
                    left, 
                    self.visual_timeline.px_per_sec,
                    self._on_visual_trim_changed
                )
                item_right = ClipGraphicsItem(
                    right,
                    self.visual_timeline.px_per_sec,
                    self._on_visual_trim_changed
                )
                
                new_items.extend([item_left, item_right])
            else:
                new_items.append(item)
        
        self.visual_timeline.items_list = new_items
        
        for item in self.visual_timeline.items_list:
            if item.scene() is None:
                self.visual_timeline.scene().addItem(item)
        
        self.visual_timeline.repack_by_order()
        
        self.tl_list.clear()
        for c in self.timeline:
            list_item = QListWidgetItem(f"{c.media.name}  [{c.media.type}]")
            list_item.setData(Qt.UserRole, c)
            self.tl_list.addItem(list_item)
    
    # --- Clip Tools ---
    
    def apply_trim_to_clip(self):
        """Applica il trim al clip."""
        clip = self._current_clip()
        if not clip:
            QMessageBox.information(self, "Select clip", "Select a clip in the timeline.")
            return
        
        try:
            start = float(self.start_edit.text())
            end_text = self.end_edit.text().strip()
            end = None if end_text == "" else float(end_text)
            
            clip.start = max(0.0, start)
            
            if end is None and clip.media.duration is not None:
                end = clip.media.duration
            
            if end is not None:
                clip.end = max(
                    clip.start + 0.2,
                    min(end, clip.media.duration or end)
                )
            else:
                clip.end = None
            
            QMessageBox.information(
                self,
                "Trim applied",
                f"Clip trimmed: start={clip.start:.2f}, "
                f"end={clip.end if clip.end is not None else 'None'}"
            )
            
            self._refresh_visual_width_for(clip)
            # Rebuild effect preview so changes reflect in preview
            self._rebuild_effect_preview_for(clip)
            
        except Exception as ex:
            QMessageBox.warning(self, "Invalid values", str(ex))
    
    def apply_title_to_clip(self):
        """Applica il titolo al clip."""
        clip = self._current_clip()
        if not clip:
            QMessageBox.information(self, "Select clip", "Select a clip in the timeline.")
            return
        
        clip.title = self.title_edit.text().strip()
        clip.title_size = int(self.title_size.value())
        
        QMessageBox.information(self, "Title set", f"Title set: {clip.title}")
        self._rebuild_effect_preview_for(clip)
    
    def apply_lut_to_clip(self):
        """Applica il LUT al clip."""
        clip = self._current_clip()
        if not clip:
            QMessageBox.information(self, "Select clip", "Select a clip in the timeline.")
            return
        
        lut = self.lut_combo.currentText()
        
        if not lut or lut.lower() == "none":
            clip.lut = "none"
        else:
            lut_path = os.path.join(self.lut_dir, lut)
            if os.path.exists(lut_path):
                clip.lut = lut
            else:
                QMessageBox.warning(
                    self,
                    "LUT not found",
                    f"Cannot find LUT file:\n{lut_path}\nSetting to 'none'."
                )
                clip.lut = "none"
        
        QMessageBox.information(self, "LUT set", f"LUT: {clip.lut}")
        self._rebuild_effect_preview_for(clip)
    
    def set_transition_for_selected(self):
        """Imposta la transizione."""
        clip = self._current_clip()
        if not clip:
            QMessageBox.information(self, "Select clip", "Select a clip in the timeline.")
            return
        
        transition = self.transition_combo.currentText()
        clip.transition = transition
        
        QMessageBox.information(self, "Transition set", f"Transition to next: {transition}")
        # No direct impact on single-clip preview

    def apply_speed_to_clip(self):
        """Applica la velocità (speed) al clip selezionato e aggiorna timeline/preview."""
        clip = self._current_clip()
        if not clip:
            QMessageBox.information(self, "Select clip", "Select a clip in the timeline.")
            return
        try:
            val = float(self.speed_spin.value()) if hasattr(self, 'speed_spin') else 1.0
            if val <= 0:
                val = 1.0
            clip.speed = float(val)
            # Update UI/timeline width
            self._refresh_visual_width_for(clip)
            # If clip is active and no baked preview, adjust playback rate; also rebuild preview
            try:
                sel_items = [it for it in self.visual_timeline.items_list if it.isSelected()]
                if sel_items and sel_items[0].clip is clip:
                    if getattr(clip, 'effect_preview_path', None):
                        self.player.setPlaybackRate(1.0)
                    else:
                        self.player.setPlaybackRate(clip.speed)
            except Exception:
                pass
            self._rebuild_effect_preview_for(clip)
            QMessageBox.information(self, "Speed set", f"Playback speed: x{clip.speed:.2f}")
        except Exception as ex:
            QMessageBox.warning(self, "Invalid speed", str(ex))
    
    def choose_bg_music(self):
        """Sceglie la musica di sottofondo."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select background music",
            str(Path.home()),
            "Audio files (*.mp3 *.wav *.m4a)"
        )
        
        if path:
            self.project_bg_music = path
            self.bg_music_label.setText(os.path.basename(path))
    
    def _current_clip(self) -> Optional[TimelineClip]:
        """Ritorna il clip correntemente selezionato."""
        sel = self.tl_list.currentItem()
        if sel:
            return sel.data(Qt.UserRole)
        
        sel_items = [it for it in self.visual_timeline.items_list if it.isSelected()]
        if sel_items:
            return sel_items[0].clip
        
        return None
    
    def _refresh_visual_width_for(self, clip: TimelineClip):
        """Aggiorna la larghezza visuale di un clip."""
        for item in self.visual_timeline.items_list:
            if item.clip is clip:
                item._update_rect_width()
                break
        
        self.visual_timeline.repack_by_order()
    
    def _refresh_lut_list(self):
        """Aggiorna la lista dei LUT."""
        self.lut_combo.clear()
        self.lut_combo.addItem("none")
        
        if os.path.isdir(self.lut_dir):
            for filename in os.listdir(self.lut_dir):
                if filename.lower().endswith(".cube"):
                    self.lut_combo.addItem(filename)
    
    # --- Zoom ---
    
    def zoom_in(self):
        """Aumenta lo zoom."""
        self.visual_timeline.zoom_in()
    
    def zoom_out(self):
        """Diminuisce lo zoom."""
        self.visual_timeline.zoom_out()
    
    def fit_timeline(self):
        """Adatta la timeline."""
        self.visual_timeline.fit_timeline()
    
    # --- Preview Generation ---
    
    def _prepare_clip_previews(self, clip: TimelineClip):
        """Prepara le preview per un clip."""
        if clip.preview_dir and (clip.thumb_paths or clip.waveform_path):
            return
        
        res_map = {0: 360, 1: 480, 2: 640, 3: 720}
        idx = getattr(self, 'preview_res_combo', None)
        if idx is not None and isinstance(idx, QComboBox):
            sel = self.preview_res_combo.currentIndex()
        else:
            sel = 2

        proxy_width = res_map.get(sel, 640)
        use_proxies = getattr(self, 'proxy_checkbox', None) and getattr(self.proxy_checkbox, 'isChecked', lambda: False)()

        worker = PreviewWorker(
            clip, self._temp_preview_root, self._thumbs_cache, self._wave_cache,
            proxy_width=proxy_width, proxy_enabled=bool(use_proxies)
        )
        worker.signals.started.connect(self._on_preview_started)
        worker.signals.done.connect(self._on_preview_ready)
        self.pool.start(worker)

    def _rebuild_effect_preview_for(self, clip: TimelineClip):
        """Queue building of an effect preview for the clip (LUT/title/speed/trim)."""
        try:
            worker = EffectPreviewWorker(clip, self._temp_preview_root, self.lut_dir)
            worker.signals.started.connect(self._on_preview_started)
            worker.signals.done.connect(self._on_preview_ready)
            try:
                worker.signals.failed.connect(lambda c, e: self._on_effect_preview_failed(c, e))
            except Exception:
                pass
            self.pool.start(worker)
        except Exception:
            pass

    def _on_effect_preview_failed(self, clip: TimelineClip, err: str):
        try:
            if hasattr(self, 'preview_status_label'):
                self.preview_status_label.setText("")
                self.preview_status_label.setVisible(False)
            if hasattr(self, 'preview_progress'):
                self.preview_progress.setVisible(False)
        except Exception:
            pass

    @Slot(object)
    def _on_preview_started(self, clip: TimelineClip):
        """Mostra UI di progress."""
        try:
            self.preview_status_label.setText(f"Processing: {clip.media.name}")
            self.preview_status_label.setVisible(True)
            self.preview_progress.setVisible(True)
            if hasattr(self, 'btn_add_to_tl'):
                self.btn_add_to_tl.setEnabled(False)
            try:
                clip._processing = True
                for item in self.visual_timeline.items_list:
                    if item.clip is clip:
                        item.update()
                        break
            except Exception:
                pass
        except Exception:
            pass

    @Slot(object)
    def _on_preview_ready(self, clip: TimelineClip):
        """Callback quando le preview sono pronte."""
        for item in self.visual_timeline.items_list:
            if item.clip is clip:
                item._load_cached_pixmaps()
                try:
                    clip._processing = False
                except Exception:
                    pass
                item._update_rect_width()
                item.update()
                break
    
        try:
            self.preview_progress.setVisible(False)
            self.preview_status_label.setVisible(False)
            if hasattr(self, 'btn_add_to_tl'):
                self.btn_add_to_tl.setEnabled(True)
        except Exception:
            pass

        try:
            if getattr(clip, 'proxy_path', None):
                self._proxy_cache[clip.media.path] = clip.proxy_path
        except Exception:
            pass

        # If an effect preview was just created and this clip is selected, use it
        try:
            if getattr(clip, 'effect_preview_path', None):
                sel_items = [it for it in self.visual_timeline.items_list if it.isSelected()]
                if sel_items and sel_items[0].clip is clip:
                    self.player.setSource(QUrl.fromLocalFile(clip.effect_preview_path))
                    self.player.setPlaybackRate(1.0)
        except Exception:
            pass

    def _selected_clip(self) -> Optional[TimelineClip]:
        """Return currently selected clip."""
        sel = self.tl_list.currentItem()
        if sel:
            return sel.data(Qt.UserRole)

        vis = [it for it in self.visual_timeline.items_list if it.isSelected()]
        if vis:
            return vis[0].clip

        return None

    def _on_clear_proxy_clicked(self):
        """Clear proxy for selected clip."""
        clip = self._selected_clip()
        if not clip:
            QMessageBox.information(self, "No selection", "Select a clip first")
            return

        try:
            p = getattr(clip, 'proxy_path', None)
            if p and os.path.exists(p):
                os.remove(p)
            clip.proxy_path = None
            if clip.media.path in self._proxy_cache:
                del self._proxy_cache[clip.media.path]
            QMessageBox.information(self, "Cleared", "Proxy cleared for selected clip")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not clear proxy: {e}")

    def _on_regenerate_proxy_clicked(self):
        """Force regeneration of proxy."""
        clip = self._selected_clip()
        if not clip:
            QMessageBox.information(self, "No selection", "Select a clip first")
            return

        try:
            p = getattr(clip, 'proxy_path', None)
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

        clip.proxy_path = None
        if clip.media.path in self._proxy_cache:
            try:
                del self._proxy_cache[clip.media.path]
            except Exception:
                pass

        try:
            prev = self.proxy_checkbox.isChecked()
            self.proxy_checkbox.setChecked(True)
            self._prepare_clip_previews(clip)
            self.proxy_checkbox.setChecked(prev)
            QMessageBox.information(self, "Queued", "Proxy regeneration queued in background")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not queue proxy regeneration: {e}")
    
    # --- Save/Load/Export ---
    
    def save_project(self):
        """Salva il progetto."""
        path, _ = QFileDialog.getSaveFileName(self, "Save project", str(Path.home()), "JSON (*.json)")
        
        if not path:
            return
        
        data = {
            "media": [mi.path for mi in self.media_items],
            "timeline": [clip.to_dict() for clip in self.timeline],
            "bg_music": self.project_bg_music
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        QMessageBox.information(self, "Saved", f"Project saved to {path}")
    
    def load_project(self):
        """Carica un progetto."""
        path, _ = QFileDialog.getOpenFileName(self, "Load project", str(Path.home()), "JSON (*.json)")
        
        if not path:
            return
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.media_items = []
        self.lib_list.clear()
        
        for media_path in data.get("media", []):
            if os.path.exists(media_path):
                self._add_media_to_library(media_path)
        
        self.timeline = []
        self.tl_list.clear()
        vis_clips = []
        
        for clip_data in data.get("timeline", []):
            clip = TimelineClip.from_dict(clip_data, self.media_items)
            if clip:
                self._prepare_clip_previews(clip)
                self.timeline.append(clip)
                
                list_item = QListWidgetItem(f"{clip.media.name} [{clip.media.type}]")
                list_item.setData(Qt.UserRole, clip)
                self.tl_list.addItem(list_item)
                
                vis_clips.append(clip)
        
        self.project_bg_music = data.get("bg_music")
        if self.project_bg_music:
            self.bg_music_label.setText(os.path.basename(self.project_bg_music))
        
        self.visual_timeline.rebuild(vis_clips)
        
        QMessageBox.information(self, "Loaded", f"Project loaded: {path}")
    
    def export_project(self):
        """Esporta il progetto come video finale."""
        if not self.timeline:
            QMessageBox.information(self, "Empty", "Add clips to timeline before export.")
            return
        
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export final video", str(Path.home() / "final.mp4"), "MP4 (*.mp4)"
        )
        
        if not out_path:
            return
        
        exporter = ProjectExporter(self.timeline, self.project_bg_music, self.lut_dir)
        
        try:
            exporter.export(out_path, self)
            QMessageBox.information(self, "Export finished", f"Export complete: {out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export error", f"Failed to export project:\n{str(e)}")
