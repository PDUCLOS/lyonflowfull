"""Chargeur de configuration personas depuis config/personas.yaml.

Le fichier YAML est le cerveau de l'interface : il définit les 3 personas,
leurs pages, leurs widgets visibles, leurs filtres par défaut, et les règles
d'auth.

Ce module ne fait QUE charger et exposer la config. La logique d'application
vit dans manager.py et auth.py.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "personas.yaml"


@lru_cache(maxsize=1)
def load_personas_config() -> dict[str, Any]:
    """Charge la config personas depuis le YAML. Cachée pour la session.

    Returns:
        Dict racine du YAML avec clés : version, default_persona, personas,
        common_pages, navigation, widgets_catalog.

    Raises:
        FileNotFoundError: si le fichier personas.yaml est absent.
        yaml.YAMLError: si le YAML est mal formé.
    """
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"personas.yaml introuvable à {_CONFIG_PATH}. "
            f"Crée config/personas.yaml avant de lancer le dashboard."
        )

    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "personas" not in config:
        raise ValueError(
            "personas.yaml mal formé : clé 'personas' manquante ou fichier vide."
        )

    return config


def get_persona_config(persona_id: str) -> dict[str, Any]:
    """Retourne la config d'un persona par son id.

    Args:
        persona_id: 'usager' | 'pro_tcl' | 'elu'

    Returns:
        Dict de config du persona.

    Raises:
        KeyError: si le persona n'existe pas dans la config.
    """
    config = load_personas_config()
    if persona_id not in config["personas"]:
        available = ", ".join(config["personas"].keys())
        raise KeyError(
            f"Persona '{persona_id}' inconnu. Disponibles : {available}"
        )
    return config["personas"][persona_id]


def list_personas() -> list[dict[str, Any]]:
    """Retourne la liste des personas avec leurs métadonnées publiques.

    Used by the persona switcher — ne pas exposer les mots de passe ici.
    """
    config = load_personas_config()
    personas = []
    for pid, pconf in config["personas"].items():
        personas.append(
            {
                "id": pid,
                "label": pconf.get("label", pid),
                "short_label": pconf.get("short_label", pid),
                "icon": pconf.get("icon", "👤"),
                "description": pconf.get("description", ""),
                "color_primary": pconf.get("color_primary", "#666"),
                "auth_required": pconf.get("access", {}).get("auth_required", False),
            }
        )
    return personas


def get_navigation(persona_id: str) -> list[dict[str, Any]]:
    """Retourne les entrées de navigation d'un persona."""
    config = load_personas_config()
    return config.get("navigation", {}).get(persona_id, [])


def get_common_pages() -> list[dict[str, Any]]:
    """Retourne les pages communes (RGPD, À propos)."""
    config = load_personas_config()
    return config.get("common_pages", [])


def get_widget_is_visible(persona_id: str, widget_name: str) -> bool:
    """Vérifie si un widget est visible pour un persona donné.

    Règle :
    - Si le widget est dans hidden_widgets → False
    - Sinon → True
    """
    pconf = get_persona_config(persona_id)
    hidden = set(pconf.get("hidden_widgets", []))
    return widget_name not in hidden
