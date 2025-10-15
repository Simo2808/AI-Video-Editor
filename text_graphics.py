"""
text_graphics.py

Provides TextGraphicsItem for text/graphics creation and animation in the timeline.
"""

from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem
from PySide6.QtGui import QFont, QColor, QPainter, QBrush
from PySide6.QtCore import QRectF, QPropertyAnimation, QPointF, Qt

class TextGraphicsItem(QGraphicsTextItem):
    """Text/graphics item with animation support."""
    def __init__(self, text, font=None, color=None, style=None, animation=None, parent=None):
        super().__init__(text, parent)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setDefaultTextColor(color or QColor(255,255,255))
        if font:
            self.setFont(font)
        self.animation_type = animation
        self._init_animation()

    def _init_animation(self):
        if self.animation_type == "typewriter":
            self.setPlainText("")
            self._full_text = self.toPlainText()
            self._timer = self.scene().views()[0].startTimer(50)
            self._char_index = 0
        elif self.animation_type == "fade":
            self.setOpacity(0)
            self._fade_anim = QPropertyAnimation(self, b"opacity")
            self._fade_anim.setDuration(1000)
            self._fade_anim.setStartValue(0)
            self._fade_anim.setEndValue(1)
            self._fade_anim.start()
        elif self.animation_type == "fly-in":
            self.setOpacity(0)
            self._fly_anim = QPropertyAnimation(self, b"pos")
            self._fly_anim.setDuration(1000)
            self._fly_anim.setStartValue(QPointF(self.x()-100, self.y()))
            self._fly_anim.setEndValue(QPointF(self.x(), self.y()))
            self._fly_anim.start()
            self.setOpacity(1)

    def timerEvent(self, event):
        if self.animation_type == "typewriter":
            if self._char_index < len(self._full_text):
                self.setPlainText(self._full_text[:self._char_index+1])
                self._char_index += 1
            else:
                self.scene().views()[0].killTimer(self._timer)

    def boundingRect(self):
        return super().boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(0,0,0,120)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.boundingRect())
        super().paint(painter, option, widget)
