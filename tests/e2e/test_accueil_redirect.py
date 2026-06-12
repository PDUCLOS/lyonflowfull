import re

from playwright.sync_api import Page, expect


def test_accueil_redirect_if_persona_set(page: Page, streamlit_server: str):
    """Test that Accueil auto-redirects if a persona is already set."""
    page.goto(streamlit_server)

    # Select "Usager" which is free access
    page.get_by_role("button", name="➡️ Adopter").first.click()

    # Wait for the redirect to the Mon Trajet page
    expect(page.get_by_text("Mon trajet")).to_be_visible()

    # Now try to go back to Accueil manually via URL
    page.goto(streamlit_server)

    # It should immediately auto-redirect back to Mon Trajet
    expect(page.get_by_text("Mon trajet")).to_be_visible()
    # It should not show the cards
    expect(page.get_by_text("Qui es-tu ?")).not_to_be_visible()
