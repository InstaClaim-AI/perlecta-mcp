"""Orchestration d'une analyse.

Le moteur ne fait aucune sortie reseau, n'execute rien de ce que contient le
document, et ne leve pas d'exception pour un document malforme : il tronque et
rapporte.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import IO

from perlecta.contrat import Anomalie, DetecteurIgnore, Gravite, Rapport, synthese_depuis
from perlecta.detection import Contexte, Indisponible, registre
from perlecta.reglage import CORPUS_DEFAUT, charger
from perlecta.typage import detecter

VERSION_MOTEUR = "0.4.0"

Source = str | Path | bytes | bytearray | IO[bytes]


def _lire(source: Source, taille_max: int) -> tuple[bytes, bool]:
    if isinstance(source, (bytes, bytearray)):
        octets = bytes(source)
    elif isinstance(source, (str, Path)):
        with open(source, "rb") as flux:
            octets = flux.read(taille_max + 1)
    else:
        octets = source.read(taille_max + 1)
    if len(octets) > taille_max:
        return octets[:taille_max], True
    return octets, False


def analyser(
    source: Source,
    type_mime: str | None = None,
    version_corpus: str = CORPUS_DEFAUT,
) -> Rapport:
    """Analyse un document et rend son rapport.

    Cette fonction ne se confine pas elle-meme : voir analyser_confine, qui est
    la fonction a appeler sauf si l'appelant confine deja.
    """
    corpus = charger(version_corpus)
    debut = time.monotonic()

    octets, tronque_taille = _lire(source, corpus.plafonds.taille_octets_max)
    empreinte = hashlib.sha256(octets).hexdigest()
    type_detecte = type_mime or detecter(octets)

    contexte = Contexte(
        octets=octets, type_detecte=type_detecte, corpus=corpus, tronque=tronque_taille
    )
    anomalies: list[Anomalie] = []
    executes: list[str] = []
    ignores: list[DetecteurIgnore] = []

    for detecteur in registre():
        if type_detecte not in detecteur.types:
            ignores.append(
                DetecteurIgnore(detecteur.nom, f"type non pris en charge : {type_detecte}")
            )
            continue
        if (time.monotonic() - debut) * 1000 > corpus.plafonds.duree_ms_max:
            ignores.append(DetecteurIgnore(detecteur.nom, "plafond de duree atteint"))
            contexte.tronque = True
            continue
        try:
            anomalies.extend(detecteur.analyser(contexte))
            executes.append(detecteur.nom)
        except Indisponible as err:
            ignores.append(DetecteurIgnore(detecteur.nom, str(err)))
        except Exception as err:  # un detecteur en echec n'interrompt pas l'analyse
            ignores.append(DetecteurIgnore(detecteur.nom, f"echec : {type(err).__name__}"))
            contexte.tronque = True

    ordonnees = tuple(
        sorted(
            anomalies,
            key=lambda a: (
                0 if a.gravite is Gravite.MAJEURE else 1,
                a.emplacement.page or 0,
                a.emplacement.position_flux or 0,
            ),
        )
    )

    return Rapport(
        empreinte=empreinte,
        taille_octets=len(octets),
        type_detecte=type_detecte,
        anomalies=ordonnees,
        synthese=synthese_depuis(ordonnees),
        version_moteur=VERSION_MOTEUR,
        version_corpus=corpus.version,
        detecteurs_executes=tuple(executes),
        detecteurs_ignores=tuple(ignores),
        duree_ms=int((time.monotonic() - debut) * 1000),
        tronque=contexte.tronque,
    )
