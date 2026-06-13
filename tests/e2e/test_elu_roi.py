"""E2E test: login Élu et navigation vers Simulateur.

Ce test vérifie le flow complet :
1. Ouverture de l'accueil (splash cards persona)
2. Sélection du persona Élu via la carte "Adopter" (auth requise)
3. Authentification avec le mot de passe de test
4. Redirection vers la landing Élu (Synthèse Exécutive)
5. Navigation vers la page Elu_4_Simulateur via le lien sidebar
"""

from playwright.sync_api import Page, expect


def test_elu_roi(page: Page, streamlit_server: str):
    """Test switching to Elu persona, authenticating, and viewing ROI calculator."""
    page.goto(streamlit_server)

    # Wait for app load — splash screen with persona cards
    expect(page.get_by_text("Qui es-tu ?")).to_be_visible(timeout=10000)

    # Clique sur "Adopter" de la carte Élu (2e bouton Adopter)
    all_adopter_buttons = page.get_by_role("button", name="Adopter").all()
    assert len(all_adopter_buttons) >= 2, "Les cartes Élu et Pro TCL doivent être visibles"
    elu_adopt_btn = all_adopter_buttons[1]
    elu_adopt_btn.click()

    # Vérifie le formulaire d'authentification
    expect(page.get_by_text("Authentification requise")).to_be_visible()

    # Authentification
    page.get_by_label("Mot de passe").fill("testpwd")
    page.get_by_role("button", name="Se connecter").click()

    # Landing Élu = Synthèse Exécutive
    expect(page.get_by_text("Synthèse Exécutive")).to_be_visible(timeout=10000)

    # Navigation vers Simulateur via la sidebar
    # Sprint 10: sidebar avec liens texte, plus de selectbox
    sidebar = page.locator("[data-testid='stSidebarNav']")
    # Cherche le lien "Simulateur" dans la section Élu
    simulateur_link = sidebar.get_by_text("Simulateur").first
    expect(simulateur_link).to_be_visible()
    simulateur_link.click()

    # Vérifie que la page Simulateur est affichée
    expect(page.get_by_role("heading", name="Simulateur")).to_be_visible(timeout=10000)
