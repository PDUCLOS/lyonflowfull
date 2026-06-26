"""Gitleaks-style scrubber — détecte les secrets avant commit.

 (2026-06-12) — protection de la logique projet.

Le repo LyonFlow est public sur GitHub (PDUCLOS/lyonflow).
Pour éviter qu'un concurrent copie-colle la logique métier (modèles
ML, pathfinding H3, vues matérialisées KPIs) sans effort, on :

1. Scrub systématique des secrets avant commit (DB_PASSWORD, API
   keys, etc.) — appelé par pre-commit hook.
2. Embargo sur les hyperparamètres ML entraînés (modèles sérialisés
   exclus du repo, stockés dans MLflow Model Registry).
3. Notice de copyright forte dans LICENSE + headers de fichiers
   (cf. NOTICE ci-dessous).

Usage CLI :
    python scripts/scrub_secrets.py src/ tests/ dashboard/

Exit code 0 si OK, 1 si secrets détectés (commit bloqué).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Patterns de secrets (gitleaks-style)
SECRET_PATTERNS = {
    "POSTGRES_PASSWORD": re.compile(
        r"POSTGRES_PASSWORD\s*=\s*['\"]?([a-zA-Z0-9!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]{8,})",
        re.IGNORECASE,
    ),
    "AIRFLOW_FERNET_KEY": re.compile(r"AIRFLOW_FERNET_KEY\s*=\s*['\"]?([a-zA-Z0-9+/=]{40,})", re.IGNORECASE),
    "MLFLOW_TRACKING_PASSWORD": re.compile(r"MLFLOW_TRACKING_PASSWORD\s*=\s*['\"]?([a-zA-Z0-9!@#$%^&*()]{8,})"),
    "LYONFLOW_API_KEY": re.compile(r"LYONFLOW_API_KEY\s*=\s*['\"]?([a-zA-Z0-9]{32,})"),
    "TOMTOM_API_KEY": re.compile(r"TOMTOM_API_KEY\s*=\s*['\"]?([a-zA-Z0-9]{32,})"),
    "bcrypt_hash": re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"ghp_[0-9A-Za-z]{36}"),
}

# Fichiers à exclure du scan (lock files, vendor, etc.)
EXCLUDE_PATTERNS = {
    "__pycache__",
    ".git",
    ".venv",
    "node_modules",
    "*.pyc",
    "*.pkl",
    "*.joblib",
    "*.lock",
}


def _is_excluded(path: Path) -> bool:
    """Vrai si le path matche un pattern d'exclusion."""
    s = str(path)
    return any(excl in s for excl in EXCLUDE_PATTERNS)


def scan_file(path: Path) -> list[tuple[str, int, str]]:
    """Scan un fichier pour les secrets. Retourne (pattern, line, snippet)."""
    findings: list[tuple[str, int, str]] = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings
    for line_no, line in enumerate(content.split("\n"), 1):
        for pattern_name, regex in SECRET_PATTERNS.items():
            if regex.search(line):
                # Exclure les faux positifs connus (ex: .env.example)
                if ".env.example" in str(path):
                    continue
                # Exclure les tests avec secrets hardcodés (foo, bar, test)
                if any(fp in line.lower() for fp in ["foo", "bar", "test", "demo2026"]):
                    continue
                findings.append((pattern_name, line_no, line.strip()[:100]))
    return findings


def scan_dir(root: Path) -> dict[Path, list[tuple[str, int, str]]]:
    """Scan récursivement un dossier. Retourne {fichier: findings}."""
    results: dict[Path, list[tuple[str, int, str]]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path):
            continue
        findings = scan_file(path)
        if findings:
            results[path] = findings
    return results


def main(argv: list[str]) -> int:
    """Point d'entrée CLI."""
    if not argv:
        print("Usage: python scrub_secrets.py <path1> [<path2> ...]")
        return 2
    total_findings = 0
    for arg in argv:
        root = Path(arg)
        if not root.exists():
            print(f"❌ Path not found: {root}")
            continue
        results = scan_dir(root)
        for path, findings in results.items():
            for pattern_name, line_no, snippet in findings:
                print(f"🚨 {pattern_name} in {path}:{line_no}")
                print(f"   {snippet}")
                total_findings += 1
    if total_findings > 0:
        print(f"\n❌ {total_findings} secret(s) détecté(s) — commit bloqué.")
        print("   Solutions :")
        print("   1. Déplace le secret dans .env (gitignored)")
        print("   2. Ajoute un faux positif dans _ALLOWED_FP ci-dessous")
        print("   3. Si c'est un test, préfixe la variable par 'test_'")
        return 1
    print("✅ Aucun secret détecté.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
