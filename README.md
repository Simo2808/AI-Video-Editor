# AI-Video-Editor
# 🎬 Python Video Editor (PySide6 + FFmpeg)

A fully functional **timeline-based video editor** built in Python using **PySide6** for the UI and **FFmpeg** for video processing.  
It supports drag & drop editing, clip trimming, LUT filters, text overlays, speed adjustment, transitions, fade effects, and export to video files.

---

## 🧩 Features

### 🎥 Core Editing
- Import multiple **video, audio, and image** files into a media library  
- **Drag & drop** media directly into the timeline  
- **Trim, move, duplicate** clips freely across multiple tracks  
- **Change clip speed** (0.25× to 4×, with audio pitch correction)  
- Add **fade-in / fade-out** transitions per clip (video + audio)  
- Apply **LUT filters** and **color corrections**  
- Add **text overlays** or **animated titles** directly from the timeline  

### 🖼️ Visual Timeline
- Graphical timeline with thumbnails and waveforms  
- Zoom, scroll, and snap-to-grid functions  
- Visual badges for clip speed and fade indicators  
- Context menu for fast editing (speed, fades, text, duplication)

### ⚙️ Export
- Export the full project to MP4 using **FFmpeg**  
- Optional **crossfade transitions** between clips  
- Adjustable video quality (CRF / preset) and audio bitrate  
- Add **background music** automatically during export  

### 💡 UI & Preview
- Modern dark theme (custom QSS)  
- Integrated video **preview player**  
- Asynchronous thumbnail and waveform generation (background threads)  
- **Proxy mode** for smooth playback with high-resolution media  


