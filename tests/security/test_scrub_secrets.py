"""Tests Sprint 8+ pour scrub_secrets.py.

Vérifie que le scrubber détecte correctement les secrets
(DB_PASSWORD, API keys, etc.) et ne flag pas les faux positifs
(conntenu de test, .env.example, etc.).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.scrub_secrets import (
    SECRET_PATTERNS,
    _is_excluded,
    scan_file,
)


def test_patterns_cover_known_secrets():
    """Le dictionnaire SECRET_PATTERNS doit couvrir les secrets critiques."""
    required = {
        "POSTGRES_PASSWORD",
        "AIRFLOW_FERNET_KEY",
        "MLFLOW_TRACKING_PASSWORD",
        "LYONFLOW_API_KEY",
        "TOMTOM_API_KEY",
        "bcrypt_hash",
        "private_key",
        "aws_access_key",
        "github_token",
    }
    assert required.issubset(SECRET_PATTERNS.keys()), f"Patterns manquants: {required - SECRET_PATTERNS.keys()}"


def test_detect_postgres_password(tmp_path):
    """Détecte POSTGRES_PASSWORD en clair."""
    f = tmp_path / "test.py"
    f.write_text('POSTGRES_PASSWORD="my_super_secret_pwd_42"\n')
    findings = scan_file(f)
    assert any(p == "POSTGRES_PASSWORD" for p, _, _ in findings), f"POSTGRES_PASSWORD non détecté, findings={findings}"


def test_detect_fernet_key(tmp_path):
    """Détecte AIRFLOW_FERNET_KEY (base64 44+).

    Note : la chaîne fake est volontairement ``low-entropy`` (40 'a' + 2 '=')
    pour ne pas déclencher la règle ``generic-api-key`` de gitleaks (le
    test fixture n'est PAS un vrai secret). La pattern scrub_secrets.py
    matche quand même car ``[a-zA-Z0-9+/=]{40,}`` ne nécessite pas de
    diversité de caractères.
    """
    f = tmp_path / "test.py"
    f.write_text("AIRFLOW_FERNET_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa==\n")
    findings = scan_file(f)
    assert any(p == "AIRFLOW_FERNET_KEY" for p, _, _ in findings)


def test_detect_github_token(tmp_path):
    """Détecte GitHub personal access token (ghp_xxx)."""
    f = tmp_path / "test.py"
    f.write_text("token = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz123456'\n")
    findings = scan_file(f)
    assert any(p == "github_token" for p, _, _ in findings)


def test_detect_private_key(tmp_path):
    """Détecte une clé privée RSA/EC."""
    f = tmp_path / "test.py"
    f.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF5PBbGPhqUg\n")
    findings = scan_file(f)
    assert any(p == "private_key" for p, _, _ in findings)


def test_no_false_positive_env_example(tmp_path):
    """Pas de détection dans .env.example (c'est une doc, pas un secret)."""
    f = tmp_path / ".env.example"
    f.write_text("POSTGRES_PASSWORD=demo2026\nAIRFLOW_FERNET_KEY=replace_me_with_real_fernet_key_in_prod\n")
    findings = scan_file(f)
    assert findings == [], f"Faux positifs .env.example : {findings}"


def test_no_false_positive_test_passwords(tmp_path):
    """Pas de détection sur les passwords de test (foo, bar, demo)."""
    f = tmp_path / "test_auth.py"
    f.write_text("def test_login():\n    assert authenticate('foo', 'bar') == True\n")
    findings = scan_file(f)
    assert findings == [], f"Faux positifs tests : {findings}"


def test_no_false_positive_demo_password(tmp_path):
    """Le mot de passe démo hardcodé dans auth.py ne doit pas être flaggé."""
    f = tmp_path / "auth.py"
    f.write_text('_DEMO_PASSWORD = "demo2026"  # démo Jedha\n')
    findings = scan_file(f)
    assert findings == [], f"Faux positifs demo2026 : {findings}"


def test_excluded_paths():
    """Les dossiers __pycache__, .git, .venv sont exclus."""
    assert _is_excluded(Path("/foo/__pycache__/bar.py"))
    assert _is_excluded(Path("/foo/.git/config"))
    assert _is_excluded(Path("/foo/.venv/lib/x.py"))
    assert not _is_excluded(Path("/foo/src/main.py"))
    assert not _is_excluded(Path("/foo/tests/test_x.py"))


def test_patterns_have_reasonable_count():
    """Sanity check : on a entre 5 et 30 patterns (pas trop, pas trop peu)."""
    n = len(SECRET_PATTERNS)
    assert 5 <= n <= 30, f"Nombre de patterns suspect: {n}"
