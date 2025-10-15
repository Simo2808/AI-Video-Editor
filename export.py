#!/usr/bin/env python3
"""
export.py

Gestisce l'esportazione del progetto in un video finale.
"""

import os
import tempfile
import uuid
from typing import List, Optional

from config import FFmpegConfig
from models import TimelineClip
from utils import run_cmd, safe_path_for_concat


class ProjectExporter:
    """Gestisce l'esportazione del progetto."""
    
    def __init__(
        self, 
        timeline: List[TimelineClip],
        bg_music: Optional[str],
        lut_dir: str
    ):
        """
        Inizializza l'exporter.
        
        Args:
            timeline: Lista dei clip da esportare
            bg_music: Percorso della musica di sottofondo (opzionale)
            lut_dir: Directory contenente i file LUT
        """
        self.timeline = timeline
        self.bg_music = bg_music
        self.lut_dir = lut_dir
    
    def export(self, output_path: str, parent_widget=None):
        """
        Esporta il progetto come video finale.
        
        Args:
            output_path: Percorso del file di output
            parent_widget: Widget parent per messaggi di errore (opzionale)
            
        Raises:
            RuntimeError: Se l'export fallisce
        """
        # Crea directory temporanea
        temp_dir = os.path.join(
            tempfile.gettempdir(),
            f"pyeditor_{uuid.uuid4().hex}"
        )
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Renderizza tutti i clip
            rendered_clips = self._render_all_clips(temp_dir)
            
            # Concatena o applica transizioni
            use_transitions = any(c.transition == "crossfade" for c in self.timeline)
            
            if use_transitions:
                final_video = self._concatenate_with_transitions(rendered_clips, temp_dir)
            else:
                final_video = self._concatenate_simple(rendered_clips, temp_dir)
            
            # Aggiungi musica di sottofondo se presente
            if self.bg_music:
                self._add_background_music(final_video, output_path, temp_dir)
            else:
                # Copia al percorso finale
                self._copy_to_output(final_video, output_path)
        
        except Exception as e:
            raise RuntimeError(f"Export failed: {str(e)}")
    
    def _render_all_clips(self, temp_dir: str) -> List[str]:
        """
        Renderizza tutti i clip applicando effetti.
        
        Args:
            temp_dir: Directory temporanea
            
        Returns:
            Lista di percorsi ai file renderizzati
            
        Raises:
            RuntimeError: Se il rendering fallisce
        """
        rendered_clips = []
        
        for idx, clip in enumerate(self.timeline):
            rendered_path = os.path.join(temp_dir, f"clip_{idx}.mp4")
            self._render_single_clip(clip, rendered_path)
            rendered_clips.append(rendered_path)
        
        return rendered_clips
    
    def _render_single_clip(self, clip: TimelineClip, output_path: str):
        """
        Renderizza un singolo clip con tutti gli effetti.
        
        Args:
            clip: Clip da renderizzare
            output_path: Percorso del file di output
            
        Raises:
            RuntimeError: Se il rendering fallisce
        """
        src = clip.media.path
        
        # Argomenti per trim
        start_args = []
        if clip.start and clip.start > 0:
            start_args += ["-ss", str(clip.start)]
        
        duration_args = []
        if clip.end and (clip.end > (clip.start or 0.0)):
            duration_args += ["-t", str(clip.end - (clip.start or 0.0))]
        
        # Costruisci filtri video/audio
        filters = []
        a_filters = []
        
        # LUT
        if clip.lut and clip.lut != "none":
            lut_path = os.path.join(self.lut_dir, clip.lut)
            if os.path.exists(lut_path):
                filters.append(f"lut3d=file='{lut_path}'")
        
        # Titolo
        if clip.title:
            text_esc = clip.title.replace("'", "\\'")
            draw_filter = (
                f"drawtext=text='{text_esc}':fontcolor=white:"
                f"fontsize={clip.title_size}:x={clip.title_pos}:"
                f"y=(h-{clip.title_size}-40):shadowcolor=black:shadowx=2:shadowy=2"
            )
            filters.append(draw_filter)

        # Speed (velocity)
        try:
            spd = float(getattr(clip, 'speed', 1.0) or 1.0)
        except Exception:
            spd = 1.0
        if spd != 1.0:
            # Video: setpts=PTS/speed
            filters.append(f"setpts=PTS/{spd}")
            # Audio: chain atempo within 0.5..2.0 ranges
            def atempo_chain(v: float) -> str:
                if v <= 0:
                    v = 1.0
                chain = []
                remaining = v
                while remaining > 2.0:
                    chain.append("atempo=2.0")
                    remaining /= 2.0
                while remaining < 0.5:
                    chain.append("atempo=0.5")
                    remaining *= 2.0
                chain.append(f"atempo={remaining:.6f}")
                return ",".join(chain)
            a_filters.append(atempo_chain(spd))
        
        # Comando FFmpeg
        cmd = ["ffmpeg", "-y"] + start_args + ["-i", src] + duration_args
        
        if filters:
            cmd += ["-vf", ",".join(filters)]
        if a_filters:
            cmd += ["-af", ",".join(a_filters)]
        
        cmd += [
            "-c:v", "libx264",
            "-preset", FFmpegConfig.PRESET,
            "-crf", str(FFmpegConfig.CRF),
            "-c:a", "aac",
            "-b:a", FFmpegConfig.AUDIO_BITRATE,
            output_path
        ]
        
        code, _, err = run_cmd(cmd)
        
        if code != 0:
            raise RuntimeError(f"Failed to render clip: {err}")
    
    def _concatenate_simple(self, clips: List[str], temp_dir: str) -> str:
        """
        Concatena i clip senza transizioni.
        
        Args:
            clips: Lista di percorsi ai clip
            temp_dir: Directory temporanea
            
        Returns:
            Percorso del file concatenato
            
        Raises:
            RuntimeError: Se la concatenazione fallisce
        """
        concat_list = os.path.join(temp_dir, "concat_list.txt")
        
        with open(concat_list, "w", encoding="utf-8") as f:
            for path in clips:
                f.write(f'file "{safe_path_for_concat(path)}"\n')
        
        concat_out = os.path.join(temp_dir, "concatenated.mp4")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            concat_out
        ]
        
        code, _, err = run_cmd(cmd)
        
        if code != 0:
            raise RuntimeError(f"Failed to concatenate clips: {err}")
        
        return concat_out
    
    def _concatenate_with_transitions(self, clips: List[str], temp_dir: str) -> str:
        """
        Concatena i clip con transizioni crossfade.
        
        Args:
            clips: Lista di percorsi ai clip
            temp_dir: Directory temporanea
            
        Returns:
            Percorso del file finale con transizioni
            
        Raises:
            RuntimeError: Se la concatenazione fallisce
        """
        current = clips[0]
        # Apply transition set on clip i to transition into clip i+1
        for i in range(1, len(clips)):
            next_clip = clips[i]
            out_chain = os.path.join(temp_dir, f"xfade_{i-1}.mp4")

            # Determine transition type
            try:
                tr = getattr(self.timeline[i-1], 'transition', 'none') or 'none'
            except Exception:
                tr = 'none'
            # Map friendly names
            if tr == 'crossfade':
                tr = 'fade'
            if tr == 'none':
                # Simple concat of current and next when no transition
                # Implement by concatenating two clips at this step
                cmd = [
                    "ffmpeg", "-y",
                    "-i", current,
                    "-i", next_clip,
                    "-filter_complex",
                    "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
                    "-map", "[v]",
                    "-map", "[a]",
                    "-c:v", "libx264",
                    "-preset", FFmpegConfig.PRESET,
                    "-crf", str(FFmpegConfig.CRF),
                    "-c:a", "aac",
                    "-b:a", FFmpegConfig.AUDIO_BITRATE,
                    out_chain
                ]
            else:
                # Use xfade transition (video); audio simple crossfade is not handled here
                cmd = [
                    "ffmpeg", "-y",
                    "-i", current,
                    "-i", next_clip,
                    "-filter_complex",
                    f"[0:v][1:v]xfade=transition={tr}:duration={FFmpegConfig.CROSSFADE_DURATION}:offset=1,format=yuv420p",
                    "-c:v", "libx264",
                    "-preset", FFmpegConfig.PRESET,
                    "-crf", str(FFmpegConfig.CRF),
                    "-c:a", "aac",
                    "-b:a", FFmpegConfig.AUDIO_BITRATE,
                    out_chain
                ]

            code, _, err = run_cmd(cmd)
            if code != 0:
                raise RuntimeError(f"Failed transition step: {err}")

            current = out_chain

        return current
    
    def _add_background_music(self, video_path: str, output_path: str, temp_dir: str):
        """
        Aggiunge musica di sottofondo al video.
        
        Args:
            video_path: Percorso del video
            output_path: Percorso del file finale
            temp_dir: Directory temporanea
            
        Raises:
            RuntimeError: Se l'aggiunta della musica fallisce
        """
        # Processa la musica (abbassa il volume)
        music_adj = os.path.join(temp_dir, "bg.aac")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", self.bg_music,
            "-filter:a", f"volume={FFmpegConfig.VOLUME_BG_MUSIC}",
            "-c:a", "aac",
            "-b:a", FFmpegConfig.AUDIO_BITRATE,
            music_adj
        ]
        
        code, _, err = run_cmd(cmd)
        
        if code != 0:
            raise RuntimeError(f"Failed to process music: {err}")
        
        # Mixa video audio + background music
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_adj,
            "-filter_complex",
            "[0:a]volume=1[a0];[1:a]volume=1[a1];[a0][a1]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", FFmpegConfig.AUDIO_BITRATE,
            output_path
        ]
        
        code, _, err = run_cmd(cmd)
        
        if code != 0:
            raise RuntimeError(f"Failed to mix background music: {err}")
    
    def _copy_to_output(self, source: str, destination: str):
        """
        Copia il file finale alla destinazione.
        
        Args:
            source: File sorgente
            destination: Destinazione
            
        Raises:
            RuntimeError: Se la copia fallisce
        """
        try:
            os.replace(source, destination)
        except Exception:
            # Fallback: usa ffmpeg per copiare
            cmd = [
                "ffmpeg", "-y",
                "-i", source,
                "-c", "copy",
                destination
            ]
            
            code, _, err = run_cmd(cmd)
            
            if code != 0:
                raise RuntimeError(f"Failed to produce final output: {err}")
