"""META_INSTRUCTION : une metadonnee prend une forme imperative.

Dictionnaire d'information du document et paquet XMP pour un PDF, proprietes
du paquet pour un document bureautique. La forme imperative est reconnue par
des motifs declares au corpus : verbes a l'imperatif, adresse a la deuxieme
personne, formules du type « ignore », « oublie », « tu dois », « agis
comme ». Jamais par un modele de langage : la metadonnee est une donnee
hostile, elle n'est pas transmise, elle est comparee a des expressions
regulieres. Gravite mineure, c'est un signal.
"""

from __future__ import annotations

import re
from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._metadonnees import metadonnees, types_avec_metadonnees
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "META_INSTRUCTION"


def _motifs(corpus: Corpus) -> list[tuple[re.Pattern[str], str]]:
    cle = "meta_instruction.motifs"
    compiles: list[tuple[re.Pattern[str], str]] | None = corpus.donnees.get(cle)
    if compiles is None:
        compiles = []
        for entree in corpus.liste("motifs_instruction"):
            try:
                compiles.append(
                    (
                        re.compile(str(entree["motif"]), re.IGNORECASE | re.UNICODE | re.DOTALL),
                        str(entree.get("libelle", entree["motif"])),
                    )
                )
            except (KeyError, TypeError, re.error):
                continue
        corpus.donnees[cle] = compiles
    return compiles


class MetaInstruction:
    nom: str = CODE
    types: tuple[str, ...] = types_avec_metadonnees()

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        motifs = _motifs(contexte.corpus)
        anomalies: list[Anomalie] = []
        for metadonnee in metadonnees(contexte):
            libelles = [libelle for motif, libelle in motifs if motif.search(metadonnee.valeur)]
            if not libelles:
                continue
            mesure: dict[str, Any] = {"champ": metadonnee.champ, "motifs": libelles}
            anomalies.append(
                Anomalie(
                    code=CODE,
                    gravite=contexte.corpus.gravite(CODE),
                    emplacement=Emplacement(partie=metadonnee.partie),
                    extrait=contexte.extrait(metadonnee.valeur),
                    mesure=mesure,
                    explication=contexte.corpus.explication(CODE),
                )
            )
            if len(anomalies) >= contexte.corpus.plafonds.anomalies_max:
                contexte.tronque = True
                break
        return anomalies


inscrire(MetaInstruction())
