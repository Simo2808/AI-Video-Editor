#!/usr/bin/env python3
"""
utils.py

Funzioni utility per PyEditor: ffmpeg helpers, generazione preview, ecc.
"""

import os
import subprocess
from typing import Tuple, List


def run_cmd(cmd: List[str], timeout: int = 300) -> Tuple[int, str, str]:
    """
    Esegue un comando e ritorna codice di uscita, stdout e stderr.
    
    Args:
        cmd: Comando da eseguire come lista
        timeout: Timeout in secondi
        
    Returns:
        Tupla (codice_uscita, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return result.returncode, result.stdout, result.stderr
        
    except subprocess.TimeoutExpired:
        return -1, "", "Command timeout"
    except Exception as e:
        return -1, "", str(e)


def ensure_dir(path: str) -> str:
    """
    Assicura che una directory esista.
    
    Args:
        path: Percorso della directory
        
    Returns:
        Il percorso stesso
    """
    os.makedirs(path, exist_ok=True)
    return path


def safe_path_for_concat(path: str) -> str:
    """
    Prepara un percorso per il file concat di ffmpeg.
    Gestisce caratteri speciali e backslash su Windows.
    
    Args:
        path: Percorso originale
        
    Returns:
        Percorso escaped per concat
    """
    # Su Windows, converti backslash in forward slash
    path = path.replace("\\", "/")
    
    # Escape singoli apici
    path = path.replace("'", "'\\''")
    
    return path


def format_time(seconds: float) -> str:
    """
    Formatta secondi in formato mm:ss.
    
    Args:
        seconds: Secondi da formattare
        
    Returns:
        Stringa formattata
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def generate_thumbnails(
    video_path: str,
    output_dir: str,
    start: float,
    duration: float,
    count: int = 6,
    width: int = 240
) -> List[str]:
    """
    Genera thumbnail da un video.
    
    Args:
        video_path: Percorso del video
        output_dir: Directory di output
        start: Tempo di inizio (secondi)
        duration: Durata da cui estrarre (secondi)
        count: Numero di thumbnail da generare
        width: Larghezza dei thumbnail
        
    Returns:
        Lista di percorsi ai thumbnail generati
    """
    thumb_paths = []
    
    if duration <= 0 or count <= 0:
        return thumb_paths
    
    # Calcola l'intervallo tra i thumbnail
    interval = duration / max(count, 1)
    
    for i in range(count):
        timestamp = start + (i * interval)
        output_path = os.path.join(output_dir, f"thumb_{i:02d}.jpg")
        
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-vf", f"scale={width}:-2",
            output_path
        ]
        
        code, _, _ = run_cmd(cmd, timeout=10)
        
        if code == 0 and os.path.exists(output_path):
            thumb_paths.append(output_path)
    
    return thumb_paths


def generate_waveform(
    media_path: str,
    output_path: str,
    start: float,
    duration: float,
    size: Tuple[int, int] = (1000, 100)
) -> bool:
    """
    Genera un'immagine della waveform audio.
    
    Args:
        media_path: Percorso del file media
        output_path: Percorso dell'immagine di output
        start: Tempo di inizio (secondi)
        duration: Durata (secondi)
        size: Dimensioni (larghezza, altezza)
        
    Returns:
        True se la generazione ha successo
    """
    width, height = size
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", media_path,
        "-filter_complex",
        f"[0:a]showwavespic=s={width}x{height}:colors=0x4488ff[fg];color=s={width}x{height}:color=0x161616[bg];[bg][fg]overlay=format=auto",
        "-frames:v", "1",
        output_path
    ]
    
    code, _, _ = run_cmd(cmd, timeout=30)
    
    return code == 0 and os.path.exists(output_path)


def generate_proxy(
    media_path: str,
    output_dir: str,
    width: int = 640,
    audio_bitrate: str = "128k"
) -> str:
    """
    Generates a low-resolution proxy file for faster previewing.

    Returns the proxy path or empty string on failure.
    """
    ensure_dir(output_dir)
    base = os.path.basename(media_path)
    name, _ = os.path.splitext(base)
    proxy_path = os.path.join(output_dir, f"{name}_proxy_{width}w.mp4")

    # if already exists, return it
    if os.path.exists(proxy_path):
        return proxy_path

    # Use ffmpeg to create a proxy with lower resolution and codec settings
    cmd = [
        "ffmpeg", "-y",
        "-i", media_path,
        "-vf", f"scale={width}:-2",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        proxy_path
    ]

    code, _, _ = run_cmd(cmd, timeout=300)
    if code == 0 and os.path.exists(proxy_path):
        return proxy_path

    return ""