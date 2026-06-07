"""Composants UI partagés pour le dashboard LyonFlowFull."""

from dashboard.components.persona_switcher import render_persona_switcher
from dashboard.components.persona_guard import apply_persona_guard
from dashboard.components.navigation import render_sidebar_navigation
from dashboard.components.theme import inject_theme

__all__ = [
    "render_persona_switcher",
    "apply_persona_guard",
    "render_sidebar_navigation",
    "inject_theme",
]
