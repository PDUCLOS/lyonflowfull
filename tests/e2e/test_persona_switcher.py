import re

from playwright.sync_api import Page, expect


def test_persona_switcher(page: Page, streamlit_server: str):
    """Test switching from no persona to Pro TCL using the sidebar dropdown."""
    page.goto(streamlit_server)

    # Wait for the main app to load by checking the first button
    expect(page.get_by_role("button", name="Adopter").first).to_be_visible()

    # We want to test the sidebar persona switcher, NOT the main page button
    # The persona switcher is a selectbox in the sidebar
    combobox = page.locator("[data-testid='stSidebar']").get_by_role("combobox")
    combobox.click()
    # Streamlit selectboxes are best navigated with keyboard in E2E tests
    # First option is 'Usager', second is 'Pro TCL'
    combobox.press("ArrowDown")
    combobox.press("Enter")

    # Pro TCL is protected, so it should redirect back to Accueil asking for a password
    expect(page.get_by_text("Authentification requise")).to_be_visible()

    # Ensure the sidebar selector has been updated to Pro TCL
    # Streamlit selectboxes are complex DOM structures
    sidebar = page.locator("[data-testid='stSidebar']")
    expect(sidebar.get_by_text("Pro TCL")).to_be_visible()
