"""PDF_OCCULTATION : texte recouvert par un aplat opaque trace apres lui.

Le modele du peintre fait foi : ce qui est trace apres recouvre ce qui est
trace avant. Un segment est signale quand un rectangle plein, opaque, axial,
de couleur connue, non masque par un calque, trace apres lui, contient son
rectangle entier.

Une image compte, mais a trois conditions, qui ensemble mettent le document
numerise hors de cause. Elle doit etre tracee apres le texte, couvrir le
segment entier, et ne pas faire la page : une image de page entiere est
l'image d'un scan, dont le contenu n'est pas lu ici. Il faut en outre que la
page porte du texte qu'aucune image ne couvre, c'est-a-dire que le
recouvrement soit selectif. Un timbre blanc pose sur une seule ligne d'une
facture par ailleurs lisible remplit ces conditions ; une page scannee n'en
remplit aucune.

Ce qui reste hors de portee est le recouvrement par une image de page entiere,
indistinguable d'un scan sans lire les pixels : il revient a la comparaison au
rendu (PDF_DIVERGENCE_RENDU). Un trace non rectangulaire, une opacite
partielle ou un masque doux ne concluent pas non plus.
"""

from __future__ import annotations

from typing import Any

from perlecta.contrat import Anomalie
from perlecta.detection._pdf import (
    AnalysePdf,
    Segment,
    anomalies_par_ligne,
    arrondir_couleur,
    contient,
    inscrire_predicat,
    segments_attribues,
)
from perlecta.detection._scan import faits
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "PDF_OCCULTATION"
_TOLERANCE = 0.5


def _predicat(analyse: AnalysePdf, segment: Segment, corpus: Corpus) -> dict[str, Any] | None:
    if segment.invisible_par_rendu or segment.vide:
        return None
    for aplat in analyse.aplats_de(segment.page):
        if aplat.ordre < segment.ordre:
            continue
        if aplat.image or not aplat.rectangulaire or not aplat.opaque or aplat.couleur is None:
            continue
        if contient(aplat.rect, segment.rect, _TOLERANCE):
            return {
                "couvert_par": "rectangle",
                "couleur_aplat": arrondir_couleur(aplat.couleur),
                "rectangle_aplat": [round(v, 2) for v in aplat.rect],
                "ordre_texte": segment.ordre,
                "ordre_aplat": aplat.ordre,
            }
    page = faits(analyse, segment.page, corpus)
    if not page.texte_non_couvert:
        # Rien n'est a decouvert : la page est couverte en entier, pas censuree.
        return None
    for image in page.partielles:
        if image.ordre < segment.ordre:
            continue
        if contient(image.rect, segment.rect, _TOLERANCE):
            return {
                "couvert_par": "image",
                "rectangle_aplat": [round(v, 2) for v in image.rect],
                "ordre_texte": segment.ordre,
                "ordre_aplat": image.ordre,
            }
    return None


class Occultation:
    nom: str = CODE
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        return anomalies_par_ligne(contexte, CODE, segments_attribues(contexte, CODE))


inscrire_predicat(CODE, _predicat)
inscrire(Occultation())
