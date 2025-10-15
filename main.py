#!/usr/bin/env python3
"""
main.py

Entry point dell'applicazione PyEditor - Video Editor Interattivo.
"""

import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow


def main():
    """Funzione principale dell'applicazione."""
    # Crea l'applicazione Qt
    app = QApplication(sys.argv)
    app.setApplicationName("PyEditor")
    app.setOrganizationName("PyEditor")
    
    # Crea e mostra la finestra principale
    window = MainWindow()
    window.show()
    
    # Avvia l'event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()