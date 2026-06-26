"""Composants UI partagés pour le dashboard LyonFlow."""

from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.persona_switcher import render_persona_switcher
from dashboard.components.theme import inject_theme

__all__ = [
    "apply_persona_guard",
    "inject_theme",
    "render_persona_switcher",
    "render_sidebar_navigation",
]
