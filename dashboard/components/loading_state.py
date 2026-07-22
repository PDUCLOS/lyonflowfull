"""Loading states & skeletons réutilisables pour le dashboard.

 UX (2026-06-12) — Avant : les widgets faisaient des
``st.error`` brutal sur DashboardDataError, et rien pendant les
chargements DB longs. Maintenant : loading state explicite + empty
state explicite + skeleton visuel.

**Patterns** :
1. ``loading_wrapper(label, key)`` — context manager qui affiche un
   spinner Streamlit avec icône + label. Usage :
       with loading_wrapper(\"Chargement du trafic…\"):
           data = load_traffic_predictions()
2. ``empty_state(icon, title, message, action_label=None)`` — affiche
   un empty state centré avec icône, titre, message, et un bouton
   d'action optionnel.
3. ``skeleton_placeholder(n_lines=4)`` — barre placeholder grise
   pour simuler du contenu en train de charger.

Tous compatibles avec le thème dark (bg-card, primary).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import streamlit as st


@contextmanager
def loading_wrapper(
    label: str = "Chargement…",
    icon: str = "⏳",
) -> Iterator[None]:
    """Context manager qui affiche un spinner pendant le bloc.

    Args:
        label: texte affiché sous le spinner.
        icon: emoji à gauche du label.
    """
    with st.spinner(f"{icon} {label}"):
        yield


def empty_state(
    icon: str,
    title: str,
    message: str,
    action_label: str | None = None,
    action_callback: Callable | None = None,
) -> None:
    """Affiche un empty state centré avec icône, titre, message.

    Args:
        icon: emoji principal.
        title: titre en gras.
        message: message d'aide.
        action_label: texte du bouton d'action (optionnel).
        action_callback: callable appelé au clic (optionnel).
    """
    st.markdown(
        f"""
        <div style="
            background: var(--bg-card);
            border: 1px dashed var(--border-card);
            border-radius: var(--radius-md);
            padding: 2rem 1.5rem;
            text-align: center;
            margin: 1rem 0;
        ">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">{icon}</div>
            <div style="font-size: 1.1rem; font-weight: 600; color: var(--text-primary);">
                {title}
            </div>
            <div style="font-size: 0.9rem; color: var(--text-muted); margin-top: 0.4rem;">
                {message}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if action_label and action_callback and st.button(action_label, key=f"empty_action_{title[:20]}"):
        action_callback()


def skeleton_placeholder(n_lines: int = 4) -> None:
    """Affiche N barres grises pour simuler du contenu en chargement.

    Args:
        n_lines: nombre de lignes skeleton.
    """
    bars = "".join(
        f"""
        <div style="
            background: linear-gradient(90deg,
                var(--bg-card) 0%,
                var(--bg-card-alt) 50%,
                var(--bg-card) 100%);
            background-size: 200% 100%;
            height: 14px;
            border-radius: 4px;
            margin: 0.4rem 0;
            animation: shimmer 1.4s ease-in-out infinite;
            width: {100 - i * 8}%;
        "></div>
        """
        for i in range(n_lines)
    )
    st.markdown(
        f"""
        <style>
        @keyframes shimmer {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}
        </style>
        <div style="padding: 0.5rem 0;">{bars}</div>
        """,
        unsafe_allow_html=True,
    )


def data_error_to_message(e: Exception) -> str:
    """Convertit une exception en message user-friendly.

    Args:
        e: exception capturée.

    Returns:
        Message formaté pour affichage st.error.
    """
    src = getattr(e, "source", None) or "source inconnue"
    detail = getattr(e, "detail", None) or str(e)
    return f"**{src}** — {detail}"
