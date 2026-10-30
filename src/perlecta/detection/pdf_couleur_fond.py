"""PDF_COULEUR_FOND : texte de la couleur du fond effectif sous les glyphes.

Le fond effectif n'est pas le blanc de la page : c'est ce qui a ete peint
avant le texte a l'endroit des glyphes, dans l'ordre de trace. Un texte blanc
sur un bandeau bleu est lisible ; un texte bleu sur ce meme bandeau ne l'est
pas. Le detecteur echantillonne plusieurs points le long du segment et exige
que le fond y soit connu et indiscernable partout : un fond inconnu (image,
motif, trace non rectangulaire, opacite partielle) ne conclut pas.

La distance de couleur est euclidienne en RVB, normalisee entre 0 et 1, quel
que soit l'espace de couleur d'origine (gris, RVB, CMJN, indexe, ICC). Le
seuil vit au corpus. En mode de rendu invisible, la couleur est sans objet :
PDF_RENDU_INVISIBLE a deja le cas.
"""

from __future__ import annotations

from typing import Any

from perlecta.contrat import Anomalie
from perlecta.detection._pdf import (
    BLANC,
    AnalysePdf,
    Couleur,
    Segment,
    anomalies_par_ligne,
    arrondir_couleur,
    contient_point,
    distance,
    inscrire_predicat,
    luminance,
    segments_attribues,
)
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "PDF_COULEUR_FOND"
_ECHANTILLONS_MAX = 8


def _fond_sous(analyse: AnalysePdf, segment: Segment, x: float, y: float) -> Couleur | None:
    """Couleur effective du fond au point (x, y), None si elle n'est pas connue."""
    fond = BLANC
    for aplat in analyse.aplats_de(segment.page):
        if aplat.ordre > segment.ordre:
            break
        if aplat.masque_calque or not contient_point(aplat.rect, x, y):
            continue
        if aplat.image or aplat.couleur is None or not aplat.rectangulaire or aplat.alpha < 0.999:
            return None
        fond = aplat.couleur
    return fond


def _predicat(analyse: AnalysePdf, segment: Segment, corpus: Corpus) -> dict[str, Any] | None:
    if segment.invisible_par_rendu or segment.vide:
        return None
    if segment.alpha <= 0.0:
        return {"procede": "opacite_nulle", "alpha": 0.0}
    couleurs = [segment.couleur]
    if segment.mode_rendu in {2, 6}:
        couleurs.append(segment.couleur_trait)
    if any(c is None for c in couleurs):
        return None
    page = analyse.page(segment.page)
    if page is None:
        return None
    seuil = corpus.seuil("distance_couleur_fond_max")
    x0, y0, x1, y1 = segment.rect
    y = (y0 + y1) / 2.0
    n = max(2, min(_ECHANTILLONS_MAX, segment.glyphes))
    distance_max = 0.0
    fond_vu: Couleur | None = None
    echantillons = 0
    for i in range(n):
        x = x0 + (i + 0.5) / n * (x1 - x0)
        if not contient_point(page.mediabox, x, y):
            continue
        fond = _fond_sous(analyse, segment, x, y)
        if fond is None:
            return None
        echantillons += 1
        fond_vu = fond
        for couleur in couleurs:
            assert couleur is not None
            distance_max = max(distance_max, distance(couleur, fond))
    if echantillons == 0 or fond_vu is None or distance_max > seuil:
        return None
    assert segment.couleur is not None
    return {
        "couleur_texte": arrondir_couleur(segment.couleur),
        "couleur_fond": arrondir_couleur(fond_vu),
        "distance_couleur": round(distance_max, 4),
        "luminance_texte": round(luminance(segment.couleur), 3),
        "luminance_fond": round(luminance(fond_vu), 3),
        "seuil": seuil,
    }


class CouleurFond:
    nom: str = CODE
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        return anomalies_par_ligne(contexte, CODE, segments_attribues(contexte, CODE))


inscrire_predicat(CODE, _predicat)
inscrire(CouleurFond())
