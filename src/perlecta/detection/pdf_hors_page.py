"""PDF_HORS_PAGE : texte place hors de la zone affichee de la page.

La zone affichee est la CropBox, a defaut la MediaBox, heritees du noeud
parent quand la page ne les porte pas. Un segment est signale quand son
rectangle entier tombe hors de cette zone, au-dela de la marge du corpus : un
texte coupe par le bord reste partiellement visible et n'est pas signale.

/Rotate tourne la page a l'affichage sans deplacer le contenu par rapport a
ses boites : il ne change pas le dedans et le dehors. Il est rapporte dans la
mesure pour que l'integrateur situe le rectangle.
"""

from __future__ import annotations

from typing import Any

from perlecta.contrat import Anomalie
from perlecta.detection._pdf import (
    AnalysePdf,
    Segment,
    anomalies_par_ligne,
    disjoints,
    inscrire_predicat,
    segments_attribues,
)
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "PDF_HORS_PAGE"


def _predicat(analyse: AnalysePdf, segment: Segment, corpus: Corpus) -> dict[str, Any] | None:
    if segment.invisible_par_rendu or segment.vide:
        return None
    page = analyse.page(segment.page)
    if page is None:
        return None
    marge = corpus.seuil("marge_hors_page")
    if not disjoints(segment.rect, page.cropbox, marge):
        return None
    boite = "CropBox" if page.cropbox != page.mediabox else "MediaBox"
    return {
        "zone_affichee": [round(v, 2) for v in page.cropbox],
        "boite": boite,
        "rotation": page.rotation,
        "marge": marge,
    }


class HorsPage:
    nom: str = CODE
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        return anomalies_par_ligne(contexte, CODE, segments_attribues(contexte, CODE))


inscrire_predicat(CODE, _predicat)
inscrire(HorsPage())
