"""Chargement du corpus : seuils, codes et plafonds sont des donnees versionnees.

Une mise a jour du corpus ne demande pas de nouvelle version du moteur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from perlecta.contrat import Gravite

CORPUS_DEFAUT = "v1"
_RACINE = Path(__file__).parent / "corpus"


@dataclass(frozen=True)
class Plafonds:
    taille_octets_max: int
    pages_max: int
    duree_ms_max: int
    memoire_octets_max: int
    expansion_archive_max: int
    profondeur_imbrication_max: int
    extrait_caracteres_max: int
    anomalies_max: int
    operateurs_flux_max: int


@dataclass(frozen=True)
class Corpus:
    version: str
    plafonds: Plafonds
    seuils: dict[str, float]
    codes: dict[str, dict[str, Any]]
    donnees: dict[str, Any]

    def gravite(self, code: str) -> Gravite:
        return Gravite(self.codes[code]["gravite"])

    def explication(self, code: str) -> str:
        return str(self.codes[code]["explication"])

    def seuil(self, nom: str) -> float:
        return float(self.seuils[nom])

    def liste(self, nom: str) -> list[Any]:
        """Une liste de motifs ou de points de code declaree au corpus."""
        valeur = self.donnees.get(nom, [])
        return list(valeur) if isinstance(valeur, list) else []

    def dico(self, nom: str) -> dict[str, Any]:
        """Un groupe de reglages declare au corpus."""
        valeur = self.donnees.get(nom, {})
        return dict(valeur) if isinstance(valeur, dict) else {}


@lru_cache(maxsize=4)
def charger(version: str = CORPUS_DEFAUT) -> Corpus:
    chemin = _RACINE / f"{version}.json"
    if not chemin.is_file():
        raise ValueError(f"corpus inconnu : {version}")
    brut = json.loads(chemin.read_text(encoding="utf-8"))
    return Corpus(
        version=str(brut["version"]),
        plafonds=Plafonds(**brut["plafonds"]),
        seuils={k: float(v) for k, v in brut["seuils"].items()},
        codes=brut["codes"],
        donnees={
            cle: valeur
            for cle, valeur in brut.items()
            if cle not in {"version", "plafonds", "seuils", "codes"}
        },
    )
