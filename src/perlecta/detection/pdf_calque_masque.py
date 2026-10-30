"""PDF_CALQUE_MASQUE : texte dans un groupe de contenu optionnel desactive.

Les calques sont declares dans /OCProperties du catalogue ; /D /OFF liste
ceux qui sont eteints par defaut. Dans les flux, un bloc BDC … EMC portant
/OC rattache son contenu a un groupe (OCG) ou a un dictionnaire d'appartenance
(OCMD, avec sa politique). Un XObject peut aussi porter /OC. L'interprete
partage tient la pile de contenu marque, independante de q/Q, et note sur
chaque segment les calques eteints qui le masquent.
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

CODE = "PDF_CALQUE_MASQUE"


def _predicat(analyse: AnalysePdf, segment: Segment, corpus: Corpus) -> dict[str, Any] | None:
    if segment.invisible_par_rendu or segment.vide or not segment.calques_masques:
        return None
    return {"calques": sorted(set(segment.calques_masques))}


class CalqueMasque:
    nom: str = CODE
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        return anomalies_par_ligne(contexte, CODE, segments_attribues(contexte, CODE))


inscrire_predicat(CODE, _predicat)
inscrire(CalqueMasque())
