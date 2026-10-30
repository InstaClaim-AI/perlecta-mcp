"""Protocole d'un detecteur et registre.

Un detecteur recoit les octets et le contexte, et rend des anomalies. Il ne
leve pas d'exception pour un document malforme : il rend ce qu'il a trouve et
declare ce qu'il n'a pas pu faire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from perlecta.contrat import Anomalie
from perlecta.reglage import Corpus

_DEMI_PAIRES = re.compile("[\ud800-\udfff]")


@dataclass
class Contexte:
    octets: bytes
    type_detecte: str
    corpus: Corpus
    tronque: bool = False
    # Resultats intermediaires partages entre detecteurs (parcours PDF, document
    # ouvert). Jamais serialise, jamais rapporte.
    cache: dict[str, Any] = field(default_factory=dict, repr=False)

    def extrait(self, texte: str) -> str:
        """Tronque un extrait au plafond du corpus. L'extrait reste une donnee hostile."""
        maximum = self.corpus.plafonds.extrait_caracteres_max
        texte = _DEMI_PAIRES.sub("\ufffd", texte.replace("\x00", ""))
        if len(texte) <= maximum:
            return texte
        self.tronque = True
        return texte[:maximum]


class Indisponible(Exception):
    """Leve par un detecteur qui ne peut pas s'executer : dependance absente, format inadapte."""


class Detecteur(Protocol):
    nom: str
    types: tuple[str, ...]

    def analyser(self, contexte: Contexte) -> list[Anomalie]: ...


_REGISTRE: list[Detecteur] = []


def inscrire(detecteur: Detecteur) -> Detecteur:
    _REGISTRE.append(detecteur)
    return detecteur


def registre() -> tuple[Detecteur, ...]:
    return tuple(_REGISTRE)
