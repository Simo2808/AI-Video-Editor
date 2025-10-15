#!/usr/bin/env python3
"""
graphics.py

Componenti grafici della timeline: ClipGraphicsItem e VisualTimeline.
"""

import os
from typing import Callable, List, Optional

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QStyleOptionGraphicsItem, QFrame, QMenu, QGraphicsItem
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPixmap, QPainter, QFont, QCursor,
    QPolygonF, QWheelEvent, QAction, QTransform, QPainterPath
)

from config import UIConfig, AppConfig
from models import TimelineClip
from utils import format_time

class ClipGraphicsItem(QGraphicsRectItem):
    """Clip grafico draggable con trim handles e preview."""
    
    def __init__(
        self, 
        clip: TimelineClip, 
        px_per_sec_getter: Callable[[], float],
        on_trim_changed: Callable,
        parent=None
    ):
        super().__init__(parent)
        self.setCacheMode(QGraphicsRectItem.DeviceCoordinateCache)
        
        self.clip = clip
        self._get_pps = px_per_sec_getter
        self._on_trim_changed = on_trim_changed
        
        # Altezza fissa più compatta
        self.height = 60
        self.width = 120
        
        # Setup
        self.setZValue(1)
        self.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        
        # Stati interni
        self._hover = False
        self._mode = None
        self._drag_anchor_x = 0.0
        self._orig_start = self.clip.start
        self._orig_end = self.clip.end
        self._processing_phase = 0.0
        
        # Cache pixmap
        self._cached_wave: Optional[QPixmap] = None
        self._cached_thumbs: List[QPixmap] = []
        self._load_cached_pixmaps()
        
        # Timer per processing animation
        self._processing_timer = QTimer()
        self._processing_timer.setInterval(80)
        self._processing_timer.timeout.connect(self._on_processing_tick)
        if getattr(self.clip, '_processing', False):
            self._processing_timer.start()
        
        self._update_rect_width()
    
    def _load_cached_pixmaps(self):
        """Carica i pixmap in cache."""
        if self.clip.waveform_path and os.path.exists(self.clip.waveform_path):
            self._cached_wave = QPixmap(self.clip.waveform_path)
        
        self._cached_thumbs = [
            QPixmap(p) for p in self.clip.thumb_paths 
            if os.path.exists(p)
        ]
        
        try:
            if getattr(self.clip, '_processing', False):
                if not self._processing_timer.isActive():
                    self._processing_timer.start()
            else:
                if self._processing_timer.isActive():
                    self._processing_timer.stop()
        except Exception:
            pass

    def _on_processing_tick(self):
        """Advance processing animation phase and trigger repaint."""
        try:
            self._processing_phase += 0.2
            if self._processing_phase > 2.0:
                self._processing_phase = 0.0
            self.update()
        except Exception:
            pass
    
    def _update_rect_width(self):
        """Aggiorna la larghezza del rettangolo in base alla durata."""
        duration = max(self.clip.duration_effective(), UIConfig.MIN_CLIP_DURATION)
        self.width = max(120, duration * self._get_pps())
        self.setRect(0, 0, self.width, self.height)
    
    def boundingRect(self) -> QRectF:
        """Ritorna il bounding rect del clip."""
        return QRectF(0, 0, self.width, self.height)
    
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        """Disegna il clip in stile pill, con badge iniziale e miniature video, mantenendo i colori attuali."""
        rect = self.boundingRect()

        # Base color
        if self.isSelected():
            base_color = UIConfig.SELECTED_COLOR
        elif self._hover:
            base_color = UIConfig.HOVER_COLOR
        else:
            base_color = UIConfig.BASE_COLOR

        # Rounded outer pill
        radius = 10
        path = QPainterPath()
        path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        painter.setPen(QPen(QColor(70, 80, 90), 1))
        painter.setBrush(QBrush(base_color))
        painter.drawPath(path)

        inner = rect.adjusted(8, 6, -8, -6)

        # Thumbnails band
        if self._cached_thumbs:
            painter.save()
            painter.setClipRect(inner)
            n = len(self._cached_thumbs)
            w_each = inner.width() / max(n, 1)
            x = inner.left()
            for pixmap in self._cached_thumbs:
                target = QRectF(x, inner.top(), w_each, inner.height())
                source = QRectF(0, 0, pixmap.width(), pixmap.height())
                painter.drawPixmap(target, pixmap, source)
                x += w_each
            painter.restore()

        # Left badge with media type letter
        badge_rect = QRectF(inner.left(), inner.top(), 18, inner.height())
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge_rect, 8, 8)
        painter.setPen(QColor(220, 230, 240))
        painter.setFont(QFont("Segoe UI", 8, QFont.Medium))
        letter = 'A' if getattr(self.clip.media, 'type', '') == 'audio' else ('T' if getattr(self.clip, 'title', '') else 'V')
        painter.drawText(badge_rect, Qt.AlignCenter, letter)

        # Label text
        painter.setPen(QColor(230, 235, 245))
        painter.setFont(QFont("Segoe UI", 8))
        speed_suffix = "" if getattr(self.clip, 'speed', 1.0) == 1.0 else f"  x{self.clip.speed:.2f}"
        name = f"{self.clip.media.name}{speed_suffix}"
        if getattr(self.clip, 'title', ''):
            name = f"{self.clip.title} — {name}"
        text_rect = QRectF(badge_rect.right() + 6, inner.top(), inner.width() - badge_rect.width() - 12, inner.height())
        painter.drawText(text_rect, Qt.TextSingleLine | Qt.AlignVCenter, name)

        # Subtle trim handles on hover/selected
        if self._hover or self.isSelected():
            painter.setBrush(QColor(220, 230, 240, 140))
            painter.setPen(Qt.NoPen)
            h = inner.height()
            handle_w = 4
            painter.drawRoundedRect(QRectF(rect.left()+1, rect.center().y()-h/2, handle_w, h), 2, 2)
            painter.drawRoundedRect(QRectF(rect.right()-handle_w-1, rect.center().y()-h/2, handle_w, h), 2, 2)

        # Processing indicator
        if getattr(self.clip, '_processing', False):
            radius_d = 5
            cx = rect.right() - radius_d - 6
            cy = rect.top() + 6
            phase = self._processing_phase
            color = QColor(0, 180, 220)
            alpha = 120 + int(80 * abs((phase % 2) - 1))
            color.setAlpha(alpha)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), radius_d, radius_d)

        # Border accent when selected
        if self.isSelected():
            painter.setPen(QPen(QColor(0, 180, 220), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
    
    def _format_duration(self) -> str:
        """Formatta la durata del clip."""
        duration = self.clip.duration_effective()
        return f"{max(0.0, duration):.2f}s"
    
    # --- Mouse Events ---
    
    def hoverMoveEvent(self, event):
        """Gestisce il movimento del mouse sul clip."""
        x = event.pos().x()
        
        if x <= 9 or x >= self.width - 9:
            self.setCursor(QCursor(Qt.SplitHCursor))
        else:
            movable = bool(self.flags() & QGraphicsItem.ItemIsMovable)
            self.setCursor(QCursor(Qt.OpenHandCursor if movable else Qt.ArrowCursor))
        
        self._hover = True
        self.update()
        super().hoverMoveEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Gestisce l'uscita del mouse dal clip."""
        self._hover = False
        self.setCursor(QCursor(Qt.ArrowCursor))
        self.update()
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        """Gestisce il click sul clip."""
        x = event.pos().x()
        
        if x <= 9:
            self._mode = 'trim_left'
            self._drag_anchor_x = event.scenePos().x()
            self._orig_start = self.clip.start
            self._orig_end = self.clip.end
            self.setCursor(QCursor(Qt.SplitHCursor))
        elif x >= self.width - 9:
            self._mode = 'trim_right'
            self._drag_anchor_x = event.scenePos().x()
            self._orig_start = self.clip.start
            self._orig_end = self.clip.end
            self.setCursor(QCursor(Qt.SplitHCursor))
        else:
            self._mode = 'move'
            self.setCursor(QCursor(Qt.ClosedHandCursor))
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Gestisce il movimento durante il drag."""
        if self._mode in ('trim_left', 'trim_right'):
            dx_scene = event.scenePos().x() - self._drag_anchor_x
            secs_delta = dx_scene / self._get_pps()
            
            if self._mode == 'trim_left':
                self._handle_trim_left(secs_delta)
            else:
                self._handle_trim_right(secs_delta)
            
            self._update_rect_width()
            self.update()
            
            if callable(self._on_trim_changed):
                self._on_trim_changed(self.clip)
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Gestisce il rilascio del mouse."""
        super().mouseReleaseEvent(event)
        
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        
        if self._mode == 'move':
            if view:
                self.setY(view.TRACK_OFFSET_Y)
            if self.x() < 0:
                self.setX(0)
            if view and hasattr(view, "notify_item_moved"):
                view.notify_item_moved()
        elif self._mode in ('trim_left', 'trim_right'):
            if view:
                view.repack_by_order()
        
        self._mode = None
        self.setCursor(QCursor(Qt.ArrowCursor))
        
        if not getattr(self.clip, '_processing', False):
            try:
                self._processing_timer.stop()
            except Exception:
                pass
    
    def _handle_trim_left(self, secs_delta: float):
        """Gestisce il trim sinistro."""
        new_start = max(0.0, (self._orig_start or 0.0) + secs_delta)
        base_end = self.clip.end if self.clip.end is not None else (self.clip.media.duration or 0.0)
        
        if base_end - new_start < UIConfig.MIN_CLIP_DURATION:
            new_start = max(0.0, base_end - UIConfig.MIN_CLIP_DURATION)
        
        self.clip.start = float(new_start)
    
    def _handle_trim_right(self, secs_delta: float):
        """Gestisce il trim destro."""
        base_end_orig = self._orig_end if self._orig_end is not None else (self.clip.media.duration or 0.0)
        new_end = base_end_orig + secs_delta
        max_end = self.clip.media.duration or new_end
        new_end = min(max_end, new_end)
        
        if new_end - (self.clip.start or 0.0) < UIConfig.MIN_CLIP_DURATION:
            new_end = (self.clip.start or 0.0) + UIConfig.MIN_CLIP_DURATION
        
        self.clip.end = float(new_end)


class VisualTimeline(QGraphicsView):
    """Timeline visuale con righello, zoom, drag & drop e playhead."""
    
    # Signals
    orderChanged = Signal(list)
    clipSelected = Signal(object)
    trimChanged = Signal(object)
    scrubbed = Signal(float)
    
    # Altezza del ruler - MOLTO PIÙ COMPATTA
    RULER_HEIGHT = 40
    TRACK_OFFSET_Y = 48  # Uguale al ruler height
    
    def __init__(self, parent=None):
        """Inizializza la timeline visuale."""
        super().__init__(parent)
        
        # Setup scene
        self.setScene(QGraphicsScene(self))
        self.scene().setItemIndexMethod(QGraphicsScene.NoIndex)
        
        # Rendering
        self.setRenderHints(
            QPainter.Antialiasing | 
            QPainter.SmoothPixmapTransform | 
            QPainter.TextAntialiasing
        )
        self.setBackgroundBrush(UIConfig.BG_COLOR)
        self.setFrameShape(QFrame.NoFrame)
        
        # OpenGL viewport se disponibile
        try:
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            self.setViewport(QOpenGLWidget())
        except Exception:
            pass
        
        # Data
        self.items_list: List[ClipGraphicsItem] = []
        self.clips: List[TimelineClip] = []
        
        # Zoom
        self._zoom = 1.0
        
        # Playhead
        self.playhead_sec = 0.0
        self._scrubbing = False
        
        # Throttling per scrubbing
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setInterval(AppConfig.THROTTLE_INTERVAL_MS)
        self._throttle_timer.timeout.connect(self._flush_throttled_events)
        self._pending_scrub_sec = None
        
        # UI Settings - Altezza minima più compatta
        self.setMinimumHeight(160)
        self.setMaximumHeight(260)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        
        # Context menu actions
        self._setup_context_menu()
    
    def _setup_context_menu(self):
        """Configura le azioni del context menu."""
        self.act_split = QAction("Split at Playhead", self)
        self.act_remove = QAction("Remove Selected Clip", self)
        self.act_duplicate = QAction("Duplicate Clip", self)
        self.act_properties = QAction("Clip Properties", self)
        self.act_apply_trim = QAction("Apply Trim (to tools)", self)
        self.act_apply_title = QAction("Apply Title (to tools)", self)
        self.act_apply_lut = QAction("Apply LUT (to tools)", self)
        self.act_set_transition = QAction("Set Transition (to tools)", self)
        self.act_zoom_in = QAction("Zoom In", self)
        self.act_zoom_out = QAction("Zoom Out", self)
        self.act_fit = QAction("Fit Timeline", self)
        
        self.act_zoom_in.triggered.connect(self.zoom_in)
        self.act_zoom_out.triggered.connect(self.zoom_out)
        self.act_fit.triggered.connect(self.fit_timeline)
    
    def px_per_sec(self) -> float:
        """Ritorna i pixel per secondo correnti."""
        return max(10.0, UIConfig.BASE_PX_PER_SEC * self._zoom)
    
    # --- Zoom Methods ---
    
    def zoom_in(self):
        """Aumenta lo zoom."""
        self._zoom = min(8.0, self._zoom * 1.25)
        self.repack_by_order()
    
    def zoom_out(self):
        """Diminuisce lo zoom."""
        self._zoom = max(0.2, self._zoom / 1.25)
        self.repack_by_order()
    
    def fit_timeline(self):
        """Adatta la timeline alla larghezza della viewport."""
        width_sum = sum(it.width for it in self.items_list)
        width_sum += UIConfig.GAP * (len(self.items_list) - 1 if self.items_list else 0)
        
        viewport_width = max(self.viewport().width(), 1)
        
        if width_sum <= 0:
            return
        
        target_zoom = ((viewport_width - 80) / max(width_sum, 1)) * self._zoom
        self._zoom = max(0.2, min(8.0, target_zoom))
        self.repack_by_order()
    
    def wheelEvent(self, event: QWheelEvent):
        """Gestisce lo zoom con Ctrl+Wheel."""
        from PySide6.QtWidgets import QApplication
        
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            super().wheelEvent(event)
    
    # --- Timeline Management ---
    
    def clear_all(self):
        """Pulisce la timeline."""
        self.scene().clear()
        self.items_list.clear()
        self.clips.clear()
        self.playhead_sec = 0.0
    
    def rebuild(self, clips: List[TimelineClip]):
        """Ricostruisce la timeline con supporto per text/graphics clips."""
        from text_graphics import TextGraphicsItem
        self.clear_all()
        self.clips = list(clips)

        if not clips:
            self.scene().setSceneRect(0, 0, 1000, self.RULER_HEIGHT)
            self.viewport().update()
            return

        px_per_sec = self.px_per_sec()
        x = 0.0

        for clip in clips:
            if hasattr(clip, "is_text_graphics") and clip.is_text_graphics:
                item = TextGraphicsItem(
                    clip.text,
                    font=getattr(clip, "font", None),
                    color=getattr(clip, "color", None),
                    style=getattr(clip, "style", None),
                    animation=getattr(clip, "animation", None)
                )
            else:
                item = ClipGraphicsItem(
                    clip,
                    lambda: px_per_sec,
                    self._emit_trim_changed
                )
            item.setPos(QPointF(x, self.TRACK_OFFSET_Y))
            self.scene().addItem(item)
            self.items_list.append(item)
            x += getattr(item, "width", 120) + UIConfig.GAP

        self._update_scene_rect()
        self.viewport().update()
    
    def append_clip(self, clip: TimelineClip):
        """Aggiunge un clip alla fine della timeline."""
        self.clips.append(clip)
        
        item = ClipGraphicsItem(
            clip,
            self.px_per_sec,
            self._emit_trim_changed
        )
        
        # Posiziona alla fine
        if self.items_list:
            last_item = self.items_list[-1]
            x = last_item.x() + last_item.width + UIConfig.GAP
        else:
            x = 0
        
        item.setPos(QPointF(x, self.TRACK_OFFSET_Y))
        self.scene().addItem(item)
        self.items_list.append(item)
        
        self._update_scene_rect()
        self.update()
    
    def _update_scene_rect(self):
        """Aggiorna le dimensioni della scena."""
        width_sum = sum(it.width for it in self.items_list)
        width_sum += UIConfig.GAP * (len(self.items_list) - 1 if self.items_list else 0)
        
        viewport_w = max(self.viewport().width(), 1)
        total_w = max(width_sum + 100, viewport_w)
        
        # Altezza totale: ruler + clip + padding
        total_h = self.RULER_HEIGHT + 70 
        
        self.scene().setSceneRect(0, 0, total_w, total_h)
        self.viewport().update()
    
    def repack_by_order(self):
        """Riposiziona i clip mantenendo l'ordine."""
        ordered = sorted(self.items_list, key=lambda it: it.x())
        
        x = 0.0
        for item in ordered:
            item.setPos(QPointF(x, self.TRACK_OFFSET_Y))
            x += item.width + UIConfig.GAP
        
        self.items_list = ordered
        self.clips = [it.clip for it in ordered]
        self.orderChanged.emit(self.clips)
        self._update_scene_rect()
        self.update()
    
    def ripple_delete(self, clip: TimelineClip):
        """Remove a clip and ripple the following clips."""
        to_remove = [it for it in self.items_list if it.clip is clip]
        for it in to_remove:
            try:
                if it.scene() is not None:
                    self.scene().removeItem(it)
            except Exception:
                pass
        
        self.items_list = [it for it in self.items_list if it.clip is not clip]
        self.repack_by_order()
    
    def notify_item_moved(self):
        """Callback quando un item è stato spostato."""
        self.repack_by_order()
    
    def _emit_trim_changed(self, clip: TimelineClip):
        """Emette il segnale di trim cambiato."""
        self.trimChanged.emit(clip)
    
    # --- Mouse Events ---
    
    def mousePressEvent(self, event):
        """Gestisce il click per scrubbing."""
        scene_pos = self.mapToScene(event.pos())
        
        if event.button() == Qt.LeftButton and scene_pos.y() < self.RULER_HEIGHT:
            self.set_playhead_x(scene_pos.x())
            self._scrubbing = True
            self.scrubbed.emit(self.playhead_sec)
        
        super().mousePressEvent(event)
        
        # Selezione clip
        sel_items = [it for it in self.items_list if it.isSelected()]
        if sel_items:
            self.clipSelected.emit(sel_items[0].clip)
    
    def mouseMoveEvent(self, event):
        """Gestisce il movimento durante lo scrubbing."""
        if self._scrubbing:
            scene_pos = self.mapToScene(event.pos())
            self.set_playhead_x(scene_pos.x())
            self._pending_scrub_sec = self.playhead_sec
            
            if not self._throttle_timer.isActive():
                self._throttle_timer.start()
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Termina lo scrubbing."""
        self._scrubbing = False
        super().mouseReleaseEvent(event)
    
    def _flush_throttled_events(self):
        """Flush degli eventi throttled."""
        if self._pending_scrub_sec is not None:
            self.scrubbed.emit(self._pending_scrub_sec)
            self._pending_scrub_sec = None
        self._throttle_timer.stop()
    
    # --- Playhead ---
    
    def set_playhead_seconds(self, sec: float):
        """Imposta la posizione del playhead in secondi."""
        self.playhead_sec = max(0.0, sec)
        pps = self.px_per_sec()
        x = int(self.playhead_sec * pps - self.mapToScene(0, 0).x())
        self.viewport().update(x - 10, 0, 20, self.viewport().height())
    
    def set_playhead_x(self, scene_x: float):
        """Imposta la posizione del playhead da coordinata x della scena."""
        self.playhead_sec = max(0.0, scene_x / self.px_per_sec())
        self.viewport().update()
    
    # --- Drag & Drop ---
    
    def dragEnterEvent(self, event):
        """Accetta il drag di media."""
        mime = event.mimeData()
        if mime.hasFormat("application/x-media-path") or mime.hasText():
            event.acceptProposedAction()
    
    def dragMoveEvent(self, event):
        """Accetta il move durante il drag."""
        mime = event.mimeData()
        if mime.hasFormat("application/x-media-path") or mime.hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """Gestisce il drop di un media sulla timeline."""
        mime = event.mimeData()
        path = None
        
        if mime.hasFormat("application/x-media-path"):
            path = bytes(mime.data("application/x-media-path")).decode("utf-8")
        elif mime.hasText():
            path = mime.text()
        
        if path and os.path.exists(path):
            parent = self.parent()
            while parent and not hasattr(parent, "drop_media_on_timeline"):
                parent = parent.parent()
            
            if parent and hasattr(parent, "drop_media_on_timeline"):
                parent.drop_media_on_timeline(path)
            
            event.acceptProposedAction()
    
    # --- Drawing ---
    
    def drawForeground(self, painter: QPainter, rect):
        """Disegna righello e playhead."""
        viewport_rect = self.viewport().rect()
        
        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        
        # Ruler background
        painter.fillRect(
            0, 0, 
            viewport_rect.width(), 
            self.RULER_HEIGHT, 
            QColor(24, 28, 34)
        )
        
        # Linea di separazione ruler/clips
        painter.setPen(QPen(QColor(70, 70, 80), 1))
        painter.drawLine(0, self.RULER_HEIGHT, viewport_rect.width(), self.RULER_HEIGHT)
        
        # Lanes + ticks
        self._draw_lanes_background(painter, viewport_rect)
        self._draw_ruler_ticks(painter, viewport_rect)
        
        # Playhead red line
        self._draw_playhead(painter, viewport_rect)
        
        painter.restore()
    
    def _draw_ruler_ticks(self, painter: QPainter, viewport_rect):
        """Disegna i tick del righello con stile puntinato e griglia secondi."""
        view_left = self.mapToScene(0, 0).x()
        view_right = self.mapToScene(viewport_rect.width(), 0).x()
        pps = self.px_per_sec()
        
        sec_start = max(0, int(view_left / pps) - 1)
        sec_end = int(view_right / pps) + 2
        
        # Minor dotted marks (5 subdivisions per second)
        dot_pen = QPen(QColor(90, 95, 105), 1, Qt.DotLine)
        dot_pen.setCosmetic(True)
        painter.setPen(dot_pen)
        sub_steps = 5
        for s in range(sec_start, sec_end + 1):
            for i in range(1, sub_steps):
                x = s * pps + (i * pps / sub_steps) - view_left
                if 0 <= x <= viewport_rect.width():
                    painter.drawLine(int(x), self.RULER_HEIGHT - 8, int(x), self.RULER_HEIGHT)
        
        # Major ticks + labels each second and grid lines
        painter.setPen(QPen(QColor(180, 190, 200), 1))
        painter.setFont(QFont("Segoe UI", 9))
        grid_pen = QPen(QColor(50, 55, 65), 1)
        grid_pen.setCosmetic(True)
        for s in range(sec_start, sec_end + 1):
            x = s * pps - view_left
            if 0 <= x <= viewport_rect.width():
                painter.drawLine(int(x), self.RULER_HEIGHT - 16, int(x), self.RULER_HEIGHT)
                painter.drawText(int(x) + 3, 16, format_time(s))
                painter.save()
                painter.setPen(grid_pen)
                painter.drawLine(int(x), self.RULER_HEIGHT + 1, int(x), viewport_rect.height())
                painter.restore()

    def _draw_lanes_background(self, painter: QPainter, viewport_rect):
        top = self.RULER_HEIGHT + 1
        h_total = viewport_rect.height() - top
        if h_total <= 0:
            return
        lane_h = 40
        y = top
        alt1 = QColor(28, 32, 38)
        alt2 = QColor(26, 30, 36)
        i = 0
        while y < viewport_rect.height():
            painter.fillRect(0, int(y), viewport_rect.width(), lane_h, alt1 if i % 2 == 0 else alt2)
            y += lane_h
            i += 1
    
    def _draw_playhead(self, painter: QPainter, viewport_rect):
        """Disegna il playhead rosso."""
        pps = self.px_per_sec()
        view_left = self.mapToScene(0, 0).x()
        px = self.playhead_sec * pps - view_left
        
        # Linea verticale
        painter.setPen(QPen(UIConfig.PLAYHEAD_COLOR, 2))
        painter.drawLine(int(px), 0, int(px), viewport_rect.height())
        
        # Triangolo sul righello
        painter.setBrush(UIConfig.PLAYHEAD_COLOR)
        painter.setPen(Qt.NoPen)
        
        triangle = QPolygonF([
            QPointF(px - 6, 0),
            QPointF(px + 6, 0),
            QPointF(px, 10)
        ])
        painter.drawPolygon(triangle)
    
    # --- Context Menu ---
    
    def contextMenuEvent(self, event):
        """Mostra il context menu."""
        scene_pos = self.mapToScene(event.pos())
        clicked_items = self.scene().items(scene_pos)
        clicked_clip_item = None
        for it in clicked_items:
            if isinstance(it, ClipGraphicsItem):
                clicked_clip_item = it
                break

        if clicked_clip_item:
            for it in self.items_list:
                it.setSelected(it is clicked_clip_item)
            self.clipSelected.emit(clicked_clip_item.clip)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e1e; border: 1px solid #2a2a2a; color: #ddd; }
            QMenu::item:selected { background-color: #2b2b2b; }
        """)

        menu.addAction(self.act_split)
        menu.addAction(self.act_remove)
        menu.addAction(self.act_duplicate)
        menu.addAction(self.act_properties)
        menu.addSeparator()
        menu.addAction(self.act_apply_trim)
        menu.addAction(self.act_apply_title)
        menu.addAction(self.act_apply_lut)
        menu.addAction(self.act_set_transition)
        menu.addSeparator()
        menu.addAction(self.act_zoom_in)
        menu.addAction(self.act_zoom_out)
        menu.addAction(self.act_fit)

        chosen = menu.exec(event.globalPos())

        if chosen is self.act_split:
            p = self.parent()
            while p and not hasattr(p, "split_at_playhead"):
                p = p.parent()
            if p and hasattr(p, "split_at_playhead"):
                p.split_at_playhead()
        elif chosen is self.act_remove:
            p = self.parent()
            while p and not hasattr(p, "remove_selected_clip"):
                p = p.parent()
            if p and hasattr(p, "remove_selected_clip"):
                p.remove_selected_clip()
        elif chosen is self.act_duplicate:
            p = self.parent()
            while p and not hasattr(p, "duplicate_selected_clip"):
                p = p.parent()
            if p and hasattr(p, "duplicate_selected_clip"):
                p.duplicate_selected_clip()
        elif chosen is self.act_properties:
            p = self.parent()
            while p and not hasattr(p, "show_clip_properties"):
                p = p.parent()
            if p and hasattr(p, "show_clip_properties"):
                p.show_clip_properties()
        elif chosen is self.act_apply_trim:
            p = self.parent()
            while p and not hasattr(p, "apply_trim_to_clip"):
                p = p.parent()
            if p and hasattr(p, "apply_trim_to_clip"):
                p.apply_trim_to_clip()
        elif chosen is self.act_apply_title:
            p = self.parent()
            while p and not hasattr(p, "apply_title_to_clip"):
                p = p.parent()
            if p and hasattr(p, "apply_title_to_clip"):
                p.apply_title_to_clip()
        elif chosen is self.act_apply_lut:
            p = self.parent()
            while p and not hasattr(p, "apply_lut_to_clip"):
                p = p.parent()
            if p and hasattr(p, "apply_lut_to_clip"):
                p.apply_lut_to_clip()
        elif chosen is self.act_set_transition:
            p = self.parent()
            while p and not hasattr(p, "set_transition_for_selected"):
                p = p.parent()
            if p and hasattr(p, "set_transition_for_selected"):
                p.set_transition_for_selected()
