#!/usr/bin/env python3
"""
widgets.py

Widget personalizzati per PyEditor.
"""

from PySide6.QtWidgets import QListWidget
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag


class MediaListWidget(QListWidget):
    """
    Lista widget con supporto drag & drop per i media.
    """
    
    def __init__(self, parent=None):
        """Inizializza il widget."""
        super().__init__(parent)
        
        # Abilita drag
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)
    
    def startDrag(self, supportedActions):
        """
        Inizia il drag di un item.
        
        Args:
            supportedActions: Azioni supportate
        """
        item = self.currentItem()
        
        if not item:
            return
        
        # Recupera il MediaItem
        media_item = item.data(Qt.UserRole)
        
        if not media_item:
            return
        
        # Crea mime data con il percorso del file
        mime_data = QMimeData()
        mime_data.setData("application/x-media-path", media_item.path.encode("utf-8"))
        mime_data.setText(media_item.path)
        
        # Crea e avvia il drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        
        # Esegui il drag
        drag.exec(Qt.CopyAction)