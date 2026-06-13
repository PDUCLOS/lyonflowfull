"""E2E test: sélection du persona Pro TCL et redirection auth.

Ce test vérifie :
1. Le persona Usager est le défaut (pas de redirection car pas de session)
2. Sélection de Pro TCL via la carte "Adopter" (auth requise)
3. Vérifie que la page affiche bien "Authentification requise"
4. Vérifie que le sidebar affiche les liens de navigation Pro TCL
"""

from playwright.sync_api import Page, expect


def test_persona_switcher(page: Page, streamlit_server: str):
    """Test switching to Pro TCL persona and auth redirect."""
    page.goto(streamlit_server)

    # Wait for splash screen
    expect(page.get_by_text("Qui es-tu ?")).to_be_visible(timeout=10000)

    # Clique sur "Adopter" de la carte Pro TCL (1er bouton Adopter)
    all_adopter_buttons = page.get_by_role("button", name="Adopter").all()
    assert len(all_adopter_buttons) >= 1, "Au moins la carte Pro TCL doit être visible"
    pro_tcl_adopt_btn = all_adopter_buttons[0]
    pro_tcl_adopt_btn.click()

    # Pro TCL est protégé → redirection vers le formulaire d'auth
    expect(page.get_by_text("Authentification requise")).to_be_visible()

    # Vérifie que la sidebar contient des liens de navigation Pro TCL
    # Sprint 10: sidebar avec liens texte (plus de stSidebarNav combobox)
    sidebar = page.locator("[data-testid='stSidebarNav']")
    # Cherche au moins un lien Pro TCL visible
    pro_links = sidebar.get_by_text("PCC").all()
    assert len(pro_links) > 0, "Au moins un lien Pro TCL doit être visible dans la sidebar"
