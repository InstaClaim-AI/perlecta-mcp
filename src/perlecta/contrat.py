"""Contrat public de Perlecta.

Toute la surface consommee par un integrateur tient dans ce module. Un
changement de nom ou de type ici est un changement incompatible : il casse le
test de contrat des integrateurs, et c'est le but.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Gravite(str, Enum):
    MINEURE = "mineure"
    MAJEURE = "majeure"


class Synthese(str, Enum):
    AUCUNE = "aucune_anomalie_detectee"
    MINEURES = "anomalies_mineures"
    MAJEURES = "anomalies_majeures"


@dataclass(frozen=True)
class Emplacement:
    """Ou se trouve l'anomalie. Les champs sans objet pour un format restent nuls."""

    page: int | None = None
    partie: str | None = None
    rectangle: tuple[float, float, float, float] | None = None
    position_flux: int | None = None

    def en_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "partie": self.partie,
            "rectangle": list(self.rectangle) if self.rectangle else None,
            "position_flux": self.position_flux,
        }


@dataclass(frozen=True)
class Anomalie:
    code: str
    gravite: Gravite
    emplacement: Emplacement
    extrait: str
    mesure: dict[str, Any] = field(default_factory=dict)
    explication: str = ""

    def en_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "gravite": self.gravite.value,
            "emplacement": self.emplacement.en_dict(),
            "extrait": self.extrait,
            "mesure": self.mesure,
            "explication": self.explication,
        }


@dataclass(frozen=True)
class DetecteurIgnore:
    nom: str
    motif: str

    def en_dict(self) -> dict[str, Any]:
        return {"nom": self.nom, "motif": self.motif}


@dataclass(frozen=True)
class Rapport:
    empreinte: str
    taille_octets: int
    type_detecte: str
    anomalies: tuple[Anomalie, ...]
    synthese: Synthese
    version_moteur: str
    version_corpus: str
    detecteurs_executes: tuple[str, ...]
    detecteurs_ignores: tuple[DetecteurIgnore, ...]
    duree_ms: int
    tronque: bool

    def en_dict(self) -> dict[str, Any]:
        return {
            "empreinte": self.empreinte,
            "taille_octets": self.taille_octets,
            "type_detecte": self.type_detecte,
            "anomalies": [a.en_dict() for a in self.anomalies],
            "synthese": self.synthese.value,
            "version_moteur": self.version_moteur,
            "version_corpus": self.version_corpus,
            "detecteurs_executes": list(self.detecteurs_executes),
            "detecteurs_ignores": [d.en_dict() for d in self.detecteurs_ignores],
            "duree_ms": self.duree_ms,
            "tronque": self.tronque,
        }


def synthese_depuis(anomalies: tuple[Anomalie, ...]) -> Synthese:
    """La synthese n'est pas un verdict de salubrite : elle resume les anomalies trouvees."""
    if any(a.gravite is Gravite.MAJEURE for a in anomalies):
        return Synthese.MAJEURES
    if anomalies:
        return Synthese.MINEURES
    return Synthese.AUCUNE
