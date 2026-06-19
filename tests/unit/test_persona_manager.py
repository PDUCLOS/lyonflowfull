"""Tests unitaires — src/persona/manager.

Couvre les fonctions de gestion du persona courant en session Streamlit.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def _fresh_session() -> dict:
    """Helper : simule un st.session_state vide."""
    return {}


def test_clear_current_persona_pops_session_key():
    """Sprint 15+ (audit Pro TCL 2026-06-19) — fix bug 'Changer de
    profil ne ramène pas à l'accueil'.

    ``clear_current_persona()`` doit pop le ``_SESSION_KEY`` (persona_id)
    en PLUS de clear l'auth. Sinon Accueil.py détecte un persona actif
    et re-renvoie sur la page de login au lieu d'afficher l'onboarding.
    """
    # Simule st.session_state minimal (juste assez pour les imports)
    import src.persona.manager as mgr

    # Inject une session factice via monkeypatch indirect :
    # on set les clés qu'on veut tester sur l'objet session_state.
    class _FakeSession(dict):
        def pop(self, key, default=None):
            return super().pop(key, default)

        def get(self, key, default=None):
            return super().get(key, default)

        def __contains__(self, key):
            return dict.__contains__(self, key)

        def __setitem__(self, key, value):
            dict.__setitem__(self, key, value)

    fake = _FakeSession()
    fake[mgr._SESSION_KEY] = "pro_tcl"
    fake[mgr._SESSION_AUTH_KEY] = {"pro_tcl": True, "usager": True}

    # Patch streamlit.session_state
    import streamlit as st

    original = getattr(st, "session_state", None)
    st.session_state = fake
    try:
        # Sanity : on est bien sur pro_tcl + auth
        assert mgr.get_current_persona() == "pro_tcl"
        assert mgr.is_current_persona_authenticated() is True

        # ACTION : clear_current_persona() doit pop _SESSION_KEY
        mgr.clear_current_persona()

        # ASSERTIONS
        assert mgr._SESSION_KEY not in fake, (
            f"BUG REGRESSION : _SESSION_KEY encore présent après clear_current_persona() : {dict(fake)}"
        )
        # L'auth du persona courant doit aussi être cleared
        assert fake.get(mgr._SESSION_AUTH_KEY, {}).get("pro_tcl") is None
        # L'auth des autres personas reste intacte
        assert fake.get(mgr._SESSION_AUTH_KEY, {}).get("usager") is True
    finally:
        st.session_state = original


def test_clear_current_persona_auth_does_not_pop_session_key():
    """``clear_current_persona_auth()`` ne doit clear QUE l'auth,
    pas le persona_id. C'est utilisé pour logout technique sans
    changer de persona.
    """
    import src.persona.manager as mgr

    class _FakeSession(dict):
        def pop(self, key, default=None):
            return super().pop(key, default)

        def get(self, key, default=None):
            return super().get(key, default)

        def __contains__(self, key):
            return dict.__contains__(self, key)

        def __setitem__(self, key, value):
            dict.__setitem__(self, key, value)

    fake = _FakeSession()
    fake[mgr._SESSION_KEY] = "pro_tcl"
    fake[mgr._SESSION_AUTH_KEY] = {"pro_tcl": True, "usager": True}

    import streamlit as st

    original = getattr(st, "session_state", None)
    st.session_state = fake
    try:
        mgr.clear_current_persona_auth()
        # Le persona_id doit rester (c'est le but de cette fonction)
        assert fake.get(mgr._SESSION_KEY) == "pro_tcl"
        # L'auth du persona courant est virée
        assert fake.get(mgr._SESSION_AUTH_KEY, {}).get("pro_tcl") is None
        # L'auth des autres personas est intacte
        assert fake.get(mgr._SESSION_AUTH_KEY, {}).get("usager") is True
    finally:
        st.session_state = original


def test_navigation_uses_clear_current_persona_not_auth():
    """Sprint 15+ (audit Pro TCL 2026-06-19) — vérifie que le bouton
    'Quitter' de la sidebar utilise bien ``clear_current_persona()``
    (le helper qui pop le persona_id + auth) et pas
    ``clear_current_persona_auth()`` (qui ne pop que l'auth → bug
    'redirige vers login au lieu de revenir à l'accueil').

    Le check est statique (grep sur le code source) parce que le
    composant Streamlit est difficile à monter en unit test sans
    AppTest.
    """
    nav_path = WORKSPACE / "dashboard" / "components" / "navigation.py"
    content = nav_path.read_text(encoding="utf-8")
    # Le bouton Quitter doit appeler clear_current_persona (sans _auth)
    assert "clear_current_persona()" in content, (
        "navigation.py doit appeler clear_current_persona() (pas "
        "clear_current_persona_auth) pour que le bouton 'Quitter' "
        "ramène à l'accueil."
    )
    # Pas d'APPEL à clear_current_persona_auth() dans navigation.py
    # (les commentaires/docstring peuvent mentionner l'ancien nom).
    # On cherche un appel effectif : "clear_current_persona_auth(".
    import re

    # Cherche un appel direct (avec parenthèse ouvrante)
    direct_calls = re.findall(r"clear_current_persona_auth\s*\(", content)
    assert not direct_calls, (
        f"navigation.py contient {len(direct_calls)} appel(s) à "
        f"clear_current_persona_auth() — ce helper ne pop que l'auth, "
        f"pas le persona_id. Utilisez clear_current_persona() dans le "
        f"bouton 'Quitter' pour revenir à l'accueil."
    )
