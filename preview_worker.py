#!/usr/bin/env python3
"""
preview_worker.py

Worker asincrono per generare preview (thumbnail e waveform) dei clip.
"""

import os
import uuid
from typing import Dict, List

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from config import UIConfig
from models import TimelineClip
from utils import ensure_dir, generate_thumbnails, generate_waveform, generate_proxy


class PreviewSignals(QObject):
    """Segnali emessi dal worker di preview."""
    started = Signal(object)  # Emesso quando il worker inizia (clip)
    done = Signal(object)  # Emette il TimelineClip quando pronto


class PreviewWorker(QRunnable):
    """
    Worker che genera thumbails e waveform per un clip in background.
    Riutilizza cache se disponibili.
    """
    
    def __init__(
        self,
        clip: TimelineClip,
        temp_root: str,
        thumbs_cache: Dict[str, List[str]],
        wave_cache: Dict[str, str],
        proxy_width: int = 640,
        proxy_enabled: bool = False,
    ):
        """
        Inizializza il worker.
        
        Args:
            clip: TimelineClip da processare
            temp_root: Directory root per file temporanei
            thumbs_cache: Cache condivisa dei thumbnail
            wave_cache: Cache condivisa delle waveform
        """
        super().__init__()
        self.clip = clip
        self.temp_root = temp_root
        self.thumbs_cache = thumbs_cache
        self.wave_cache = wave_cache
        # proxy support
        self.proxy_path = ""
        self.proxy_width = proxy_width
        self.proxy_enabled = bool(proxy_enabled)
        self.signals = PreviewSignals()
    
    @Slot()
    def run(self):
        """Esegue la generazione delle preview."""
        # notify started
        try:
            self.signals.started.emit(self.clip)
        except Exception:
            pass
        media = self.clip.media
        
        # Controlla cache waveform
        if media.path in self.wave_cache:
            cached_wave = self.wave_cache[media.path]
            if os.path.exists(cached_wave):
                self.clip.waveform_path = cached_wave
        
        # Controlla cache thumbnails
        if media.path in self.thumbs_cache:
            cached_thumbs = self.thumbs_cache[media.path]
            if all(os.path.exists(p) for p in cached_thumbs):
                self.clip.thumb_paths = list(cached_thumbs)
        
        # Se entrambi presenti nella cache, finito
        if self.clip.waveform_path and self.clip.thumb_paths:
            self.signals.done.emit(self.clip)
            return
        
        # Crea directory per questo clip
        clip_dir = ensure_dir(
            os.path.join(self.temp_root, f"clip_{uuid.uuid4().hex}")
        )
        self.clip.preview_dir = clip_dir

        # If proxying is enabled, attempt to generate a proxy for faster processing
        if self.proxy_enabled:
            try:
                p = generate_proxy(media.path, self.temp_root, width=self.proxy_width)
                if p:
                    self.proxy_path = p
            except Exception:
                # don't fail the whole worker if proxy generation fails
                self.proxy_path = ""
        
        # Parametri tempo
        start = self.clip.start or 0.0
        end = self.clip.end if self.clip.end is not None else (media.duration or 0.0)
        effective_dur = max(0.2, (end - start) if end > start else (media.duration or 0.0))
        
        # Genera thumbnails
        if not self.clip.thumb_paths:
            # use proxy if available
            source_for_thumbs = self.proxy_path or media.path
            new_thumbs = self._generate_thumbs_from_source(source_for_thumbs, clip_dir, start, effective_dur)
            self.clip.thumb_paths = new_thumbs
            if new_thumbs:
                self.thumbs_cache[media.path] = list(new_thumbs)
        
        # Genera waveform
        if not self.clip.waveform_path and media.type in ("video", "audio"):
            source_for_wave = self.proxy_path or media.path
            wave_path = self._generate_wave_from_source(source_for_wave, clip_dir, start, effective_dur)
            if wave_path:
                self.clip.waveform_path = wave_path
                self.wave_cache[media.path] = wave_path

        # If we generated/identified a proxy, attach it to the clip for reuse
        if self.proxy_path:
            try:
                self.clip.proxy_path = self.proxy_path
            except Exception:
                pass

        self.signals.done.emit(self.clip)
    
    def _generate_thumbs(self, output_dir: str, start: float, duration: float) -> List[str]:
        """Genera thumbnail per video o immagini. Kept for backward compatibility."""
        return self._generate_thumbs_from_source(self.clip.media.path, output_dir, start, duration)
    
    def _generate_wave(self, output_dir: str, start: float, duration: float) -> str:
        """Genera waveform audio."""
        # kept for backward compatibility
        return self._generate_wave_from_source(self.clip.media.path, output_dir, start, duration)

    def _generate_thumbs_from_source(self, source_path: str, output_dir: str, start: float, duration: float) -> List[str]:
        media = self.clip.media
        if media.type == "video":
            return generate_thumbnails(
                source_path,
                output_dir,
                start,
                duration,
                count=UIConfig.THUMBNAIL_COUNT,
                width=UIConfig.THUMBNAIL_WIDTH
            )
        elif media.type == "image":
            from utils import run_cmd
            output_path = os.path.join(output_dir, "thumb_00.jpg")
            cmd = [
                "ffmpeg", "-y", "-loop", "1",
                "-i", media.path,
                "-frames:v", "1",
                "-vf", f"scale={UIConfig.THUMBNAIL_WIDTH}:-2",
                output_path
            ]
            code, _, _ = run_cmd(cmd)
            if code == 0 and os.path.exists(output_path):
                return [output_path]

        return []

    def _generate_wave_from_source(self, source_path: str, output_dir: str, start: float, duration: float) -> str:
        wave_path = os.path.join(output_dir, "wave.png")
        success = generate_waveform(
            source_path,
            wave_path,
            start,
            duration,
            size=UIConfig.WAVEFORM_SIZE
        )
        return wave_path if success else None