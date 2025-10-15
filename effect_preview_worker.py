#!/usr/bin/env python3
"""
effect_preview_worker.py

Asynchronous worker that renders an effect preview clip for a TimelineClip
(applies trim, LUT, title drawtext, and speed) to a temporary mp4 to be used
by the QMediaPlayer for accurate preview.
"""

import os
import uuid
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from models import TimelineClip
from utils import ensure_dir, run_cmd


class EffectPreviewSignals(QObject):
    started = Signal(object)
    done = Signal(object)
    failed = Signal(object, str)


class EffectPreviewWorker(QRunnable):
    def __init__(self, clip: TimelineClip, temp_root: str, lut_dir: str):
        super().__init__()
        self.clip = clip
        self.temp_root = temp_root
        self.lut_dir = lut_dir
        self.signals = EffectPreviewSignals()

    @Slot()
    def run(self):
        try:
            self.signals.started.emit(self.clip)
        except Exception:
            pass

        try:
            # Where to store effect preview
            clip_dir = getattr(self.clip, 'preview_dir', None)
            if not clip_dir:
                clip_dir = ensure_dir(os.path.join(self.temp_root, f"clip_{uuid.uuid4().hex}"))
                try:
                    self.clip.preview_dir = clip_dir
                except Exception:
                    pass

            out_path = os.path.join(clip_dir, "effect_preview.mp4")

            # Build ffmpeg args
            src = self.clip.proxy_path if getattr(self.clip, 'proxy_path', None) else self.clip.media.path
            start = float(self.clip.start or 0.0)
            # For -t, if end is None and media has duration, use media duration - start
            if self.clip.end is not None:
                dur = max(0.1, float(self.clip.end - start))
            else:
                # Fallback to 5s if unknown
                media_dur = getattr(self.clip.media, 'duration', None)
                dur = max(0.1, float((media_dur - start) if media_dur else 5.0))

            vf_filters = []
            af_filters = []

            # LUT
            if self.clip.lut and self.clip.lut != 'none':
                lut_path = os.path.join(self.lut_dir, self.clip.lut)
                if os.path.exists(lut_path):
                    vf_filters.append(f"lut3d=file='{lut_path}'")

            # Title (drawtext)
            if getattr(self.clip, 'title', ''):
                text_esc = str(self.clip.title).replace("'", "\\'")
                vf_filters.append(
                    f"drawtext=text='{text_esc}':fontcolor=white:fontsize={int(self.clip.title_size)}:x={self.clip.title_pos}:y=(h-{int(self.clip.title_size)}-40):shadowcolor=black:shadowx=2:shadowy=2"
                )

            # Speed (video setpts, audio atempo)
            spd = float(getattr(self.clip, 'speed', 1.0) or 1.0)
            if spd != 1.0:
                # Video: setpts=PTS/speed
                vf_filters.append(f"setpts=PTS/{spd}")
                # Audio: chain atempo in 0.5..2.0 chunks
                def atempo_chain(v: float) -> str:
                    if v <= 0:
                        v = 1.0
                    chain = []
                    remaining = v
                    # Decompose into factors within [0.5, 2.0]
                    while remaining > 2.0:
                        chain.append("atempo=2.0")
                        remaining /= 2.0
                    while remaining < 0.5:
                        chain.append("atempo=0.5")
                        remaining *= 2.0
                    chain.append(f"atempo={remaining:.6f}")
                    return ",".join(chain)

                af_filters.append(atempo_chain(spd))

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-t", str(dur),
                "-i", src,
            ]

            if vf_filters:
                cmd += ["-vf", ",".join(vf_filters)]
            if af_filters:
                cmd += ["-af", ",".join(af_filters)]

            cmd += [
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "25",
                "-c:a", "aac",
                "-b:a", "128k",
                out_path
            ]

            code, _, err = run_cmd(cmd, timeout=600)
            if code != 0 or not os.path.exists(out_path):
                try:
                    self.signals.failed.emit(self.clip, err or "Failed to build effect preview")
                finally:
                    return

            try:
                self.clip.effect_preview_path = out_path
            except Exception:
                pass

            self.signals.done.emit(self.clip)

        except Exception as e:
            try:
                self.signals.failed.emit(self.clip, str(e))
            except Exception:
                pass

