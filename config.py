#!/usr/bin/env python3
"""
config.py

Configurazioni e costanti dell'applicazione PyEditor.
"""

from PySide6.QtGui import QColor

# --------------------------- UI Constants ---------------------------

class UIConfig:
    """Costanti per l'interfaccia utente."""
    
    # Colori
    BG_COLOR = QColor(15, 20, 25)
    TRACK_BG = QColor(24, 28, 34)
    AUDIO_BG = QColor(20, 24, 28)
    SELECTED_COLOR = QColor(40, 46, 54)
    HOVER_COLOR = QColor(34, 40, 48)
    BASE_COLOR = QColor(30, 34, 40)
    PLAYHEAD_COLOR = QColor(0, 180, 220)
    
    # Dimensioni Timeline
    BASE_PX_PER_SEC = 100.0
    RULER_HEIGHT = 2
    TRACK_HEIGHT_VIDEO = 60
    TRACK_HEIGHT_AUDIO = 60
    PADDING = 0
    GAP = 0
    
    # Clip Graphics
    CLIP_RADIUS = 8
    HANDLE_WIDTH = 8
    MIN_CLIP_DURATION = 0.2
    
    # Preview
    THUMBNAIL_WIDTH = 240
    THUMBNAIL_COUNT = 6
    WAVEFORM_SIZE = (1000, 100)


class FFmpegConfig:
    """Configurazioni per FFmpeg."""
    
    PRESET = "fast"
    CRF = 20
    AUDIO_BITRATE = "192k"
    VOLUME_BG_MUSIC = 0.6
    CROSSFADE_DURATION = 1.0


class AppConfig:
    """Configurazioni generali dell'applicazione."""
    
    WINDOW_TITLE = "PyEditor — Timeline Interattiva"
    WINDOW_WIDTH = 1300
    WINDOW_HEIGHT = 860
    
    # Threading
    MAX_PREVIEW_THREADS = 3
    THROTTLE_INTERVAL_MS = 16  # ~60 FPS
    SEEK_THROTTLE_MS = 10
    
    # File extensions
    VIDEO_EXTENSIONS = [".mp4", ".mov", ".mkv", ".avi", ".webm"]
    AUDIO_EXTENSIONS = [".mp3", ".wav", ".aac", ".m4a", ".ogg"]
    IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".gif"]


# --------------------------- Dark Theme QSS ---------------------------

DARK_THEME_QSS = """
QMainWindow { background-color: #0f161b; color: #e6eef6; }
QWidget { color: #e6eef6; font-family: 'Segoe UI', Roboto, Arial; font-size: 9pt; }

/* General controls */
QPushButton {
    background: transparent;
    color: #e6eef6;
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 28px;
    font-size: 9pt;
    font-weight: 600;
}
QPushButton:hover {
    background: rgba(255,255,255,0.02);
}
QPushButton[primary="true"] {
    background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #00b4d6, stop:1 #00e0ff);
    color: #042026;
    border: none;
}
QPushButton[secondary="true"] {
    background: rgba(255,255,255,0.02);
}

/* Toolbar buttons: compact */
QFrame#toolbar QPushButton {
    padding: 4px 6px;
    min-height: 24px;
    font-size: 8pt;
    font-weight: 600;
}

/* Tools panel buttons: larger and more prominent */
QWidget#toolsPanel QPushButton {
    padding: 6px 8px;
    min-height: 30px;
    font-size: 9pt;
    font-weight: 600;
    border-radius: 8px;
}

/* Inputs */
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background: #0b1114;
    border: 1px solid rgba(255,255,255,0.04);
    padding: 6px 8px;
    border-radius: 6px;
    color: #e6eef6;
}

/* Lists */
QListWidget {
    background: transparent;
    border: none;
}
QListWidget::item {
    padding: 10px;
    margin: 4px 8px;
    border-radius: 8px;
}
QListWidget::item:selected {
    background: rgba(0,180,220,0.12);
    color: #e6eef6;
}

/* Toolbar */
QFrame#toolbar {
    background: transparent;
    border-bottom: 1px solid rgba(255,255,255,0.02);
    padding: 8px 12px;
}

/* Menus */
QMenu {
    background-color: #0b1114;
    border: 1px solid rgba(255,255,255,0.04);
    color: #e6eef6;
}
QMenu::item:selected { background-color: rgba(0,180,220,0.10); }

/* Subtle headings and labels */
QLabel { color: rgba(230,238,246,0.86); font-size: 8pt; font-weight: 400; }

/* ==================== SCROLLBAR STYLING ==================== */

/* Scrollbar verticale */
QScrollBar:vertical {
    background: rgba(15, 20, 25, 0.3);
    width: 12px;
    margin: 0px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background: rgba(100, 120, 140, 0.4);
    min-height: 30px;
    border-radius: 6px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(120, 140, 160, 0.6);
}

QScrollBar::handle:vertical:pressed {
    background: rgba(0, 180, 220, 0.7);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

/* Scrollbar orizzontale */
QScrollBar:horizontal {
    background: rgba(15, 20, 25, 0.3);
    height: 12px;
    margin: 0px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background: rgba(100, 120, 140, 0.4);
    min-width: 30px;
    border-radius: 6px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background: rgba(120, 140, 160, 0.6);
}

QScrollBar::handle:horizontal:pressed {
    background: rgba(0, 180, 220, 0.7);
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* ScrollArea styling */
QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

/* Corner widget tra scrollbar verticale e orizzontale */
QScrollBar::corner {
    background: transparent;
}
"""