"""
templates.py

Predefined templates for lower thirds, animated titles, credits, etc.
"""

TEMPLATES = [
    {
        "name": "Lower Third",
        "is_text_graphics": True,
        "text": "Name - Title",
        "font": None,
        "color": None,
        "style": None,
        "animation": "fly-in"
    },
    {
        "name": "Animated Title",
        "is_text_graphics": True,
        "text": "My Awesome Video",
        "font": None,
        "color": None,
        "style": "bold",
        "animation": "fade"
    },
    {
        "name": "Credits",
        "is_text_graphics": True,
        "text": "Director: ...\nCast: ...\nMusic: ...",
        "font": None,
        "color": None,
        "style": None,
        "animation": "typewriter"
    }
]
