#!/usr/bin/env python3
"""
models.py

Modelli dati per PyEditor: MediaItem e TimelineClip.
"""

import os
import subprocess
import json
from typing import Optional, List, Dict, Any


class MediaItem:
    """Rappresenta un file media nella libreria."""
    
    def __init__(self, path: str):
        """
        Inizializza un MediaItem.
        
        Args:
            path: Percorso del file media
        """
        self.path = path
        self.name = os.path.basename(path)
        self.type = self._detect_type()
        self.duration = self._probe_duration() if self.type in ("video", "audio") else None
    
    def _detect_type(self) -> str:
        """Rileva il tipo di media dall'estensione."""
        ext = os.path.splitext(self.path)[1].lower()
        
        if ext in [".mp4", ".mov", ".mkv", ".avi", ".webm"]:
            return "video"
        elif ext in [".mp3", ".wav", ".aac", ".m4a", ".ogg"]:
            return "audio"
        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".gif"]:
            return "image"
        else:
            return "unknown"
    
    def _probe_duration(self) -> Optional[float]:
        """Rileva la durata del media usando ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                self.path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
                
        except Exception:
            pass
        
        return None


class TimelineClip:
    """Rappresenta un clip nella timeline."""
    
    def __init__(self, media: MediaItem):
        """
        Inizializza un TimelineClip.
        
        Args:
            media: MediaItem associato
        """
        self.media = media
        
        # Trim parameters
        self.start: float = 0.0
        self.end: Optional[float] = None
        
        # Title overlay
        self.title: str = ""
        self.title_size: int = 36
        self.title_pos: str = "(w-text_w)/2"  # Centrato
        
        # Color grading
        self.lut: str = "none"
        
        # Transition
        self.transition: str = "none"
        # Track index (which timeline track this clip belongs to)
        self.track: int = 0

        # Playback speed (velocity). 1.0 = normal speed
        self.speed: float = 1.0

        # Preview cache
        self.preview_dir: Optional[str] = None
        self.thumb_paths: List[str] = []
        self.waveform_path: Optional[str] = None
        # Optional proxy file path for faster preview/playback
        self.proxy_path: Optional[str] = None
    
    def duration_effective(self) -> float:
        """
        Calcola la durata effettiva del clip considerando trim.
        
        Returns:
            Durata in secondi
        """
        # Base duration from media or default for images
        if self.media.duration is None:
            base = 5.0
        else:
            start = self.start or 0.0
            end = self.end if self.end is not None else self.media.duration
            base = max(0.2, end - start)

        # Apply speed scaling; guard against invalid values
        spd = self.speed if isinstance(getattr(self, 'speed', 1.0), (int, float)) else 1.0
        spd = 1.0 if spd <= 0 else float(spd)
        # Faster speed shortens effective duration; slower speed lengthens it
        return max(0.2, base / spd)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serializza il clip in dizionario.
        
        Returns:
            Dizionario con i dati del clip
        """
        return {
            "media_path": self.media.path,
            "start": self.start,
            "end": self.end,
            "title": self.title,
            "title_size": self.title_size,
            "title_pos": self.title_pos,
            "track": self.track,
            "lut": self.lut,
            "transition": self.transition,
            "proxy_path": self.proxy_path,
            "speed": self.speed
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any], media_items: List[MediaItem]) -> Optional['TimelineClip']:
        """
        Deserializza un clip da dizionario.
        
        Args:
            data: Dizionario con i dati
            media_items: Lista dei MediaItem disponibili
            
        Returns:
            TimelineClip o None se il media non è trovato
        """
        media_path = data.get("media_path")
        
        # Cerca il MediaItem corrispondente
        media = next((m for m in media_items if m.path == media_path), None)
        
        if not media:
            # Crea nuovo MediaItem se il file esiste
            if os.path.exists(media_path):
                media = MediaItem(media_path)
            else:
                return None
        
        clip = TimelineClip(media)
        clip.start = data.get("start", 0.0)
        clip.end = data.get("end")
        clip.title = data.get("title", "")
        clip.title_size = data.get("title_size", 36)
        clip.title_pos = data.get("title_pos", "(w-text_w)/2")
        clip.track = int(data.get("track", 0))
        clip.lut = data.get("lut", "none")
        clip.transition = data.get("transition", "none")
        clip.proxy_path = data.get("proxy_path")
        try:
            clip.speed = float(data.get("speed", 1.0))
        except Exception:
            clip.speed = 1.0

        return clip
