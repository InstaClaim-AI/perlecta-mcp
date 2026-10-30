"""PDF_TAILLE_NULLE : texte de taille nulle ou sous le seuil de lisibilite.

La taille effective n'est pas l'operande de Tf : c'est cette taille multipliee
par l'echelle de la matrice de texte Tm et de la matrice courante cm. Un Tf de
1 avec une echelle de 12 donne douze points, parfaitement lisible ; un Tf de
12 sous une echelle de 0,01 n'en donne pas un dixieme. L'interprete partage
calcule cette taille effective, le detecteur la compare au seuil du corpus.
"""

from __future__ import annotations

from typing import Any

from perlecta.contrat import Anomalie
from perlecta.detection._pdf import (
    AnalysePdf,
    Segment,
    anomalies_par_ligne,
    inscrire_predicat,
    segments_attribues,
)
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "PDF_TAILLE_NULLE"


def _predicat(analyse: AnalysePdf, segment: Segment, corpus: Corpus) -> dict[str, Any] | None:
    if segment.invisible_par_rendu or segment.vide:
        return None
    seuil = corpus.seuil("taille_police_min")
    if segment.taille >= seuil:
        return None
    return {"taille_police": round(segment.taille, 4), "seuil": seuil}


class TailleNulle:
    nom: str = CODE
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        return anomalies_par_ligne(contexte, CODE, segments_attribues(contexte, CODE))


inscrire_predicat(CODE, _predicat)
inscrire(TailleNulle())
