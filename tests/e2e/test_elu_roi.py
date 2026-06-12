import re

from playwright.sync_api import Page, expect


def test_elu_roi(page: Page, streamlit_server: str):
    """Test switching to Elu persona, authenticating, and viewing ROI calculator."""
    page.goto(streamlit_server)

    # Wait for app load
    expect(page.get_by_role("button", name="➡️ Adopter").first).to_be_visible()

    # Switch to Elu in the sidebar (3rd option)
    combobox = page.locator("[data-testid='stSidebar']").get_by_role("combobox")
    combobox.click()
    combobox.press("ArrowDown")
    combobox.press("ArrowDown")
    combobox.press("Enter")

    # Should ask for authentication
    expect(page.get_by_text("Authentification requise")).to_be_visible()

    # Fill password and login
    page.get_by_label("Mot de passe").fill("testpwd")
    page.get_by_role("button", name="Se connecter").click()

    # Wait for the redirection to Elu's dashboard (Accueil Élu)
    expect(page.get_by_text("Synthèse Exécutive")).to_be_visible(timeout=10000)

    # Navigate to Simulateur page (Elu_4_Simulateur)
    page.get_by_role("link", name="Elu 4 Simulateur").click()

    # Check that Simulateur is visible
    expect(page.get_by_role("heading", name="Simulateur d'aménagement")).to_be_visible()
