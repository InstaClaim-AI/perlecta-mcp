"""Reconnaissance d'une page numerisee, partagee par deux detecteurs.

Un document numerise porte l'image de la page et, par-dessus, la couche texte
produite par la reconnaissance optique, placee en mode de rendu invisible pour
rendre le document cherchable sans abimer son apparence. Les deux procedes que
Perlecta cherche s'y trouvent donc reunis sans aucune intention de dissimuler :
du texte invisible, et du texte recouvert. C'est ainsi que tout scanner
fabrique un PDF cherchable, et c'est la forme la plus courante des pieces
recues en gestion de sinistres.

Deux detecteurs ont besoin du meme fait de page pour ne pas crier au loup
dessus. Il est calcule une fois ici, et garde sur l'analyse.

Ce que cette reconnaissance laisse ouvert est assume : un document qui imite la
signature d'un scan, image pleine page et texte invisible par-dessus, n'en est
pas distinguable sans lire les pixels. C'est exactement la comparaison que fait
PDF_DIVERGENCE_RENDU, et c'est la raison pour laquelle ce detecteur n'est pas
une option dans un deploiement qui recoit des pieces d'origine externe.
"""

from __future__ import annotations

from dataclasses import dataclass

from perlecta.detection._pdf import AnalysePdf, Aplat, Rect, Segment, contient
from perlecta.detection.base import Contexte
from perlecta.reglage import Corpus

# Part de la page qu'une image doit couvrir pour passer pour l'image d'un scan.
SEUIL_PLEINE_PAGE = "image_pleine_page_part_min"
_TOLERANCE = 0.5


@dataclass(frozen=True)
class FaitsPage:
    """Ce que les deux detecteurs ont besoin de savoir d'une page, une fois pour toutes."""

    pleine_page: tuple[Aplat, ...]
    partielles: tuple[Aplat, ...]
    texte_non_couvert: bool


def _aire(r: Rect) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _calculer(analyse: AnalysePdf, numero: int, corpus: Corpus) -> FaitsPage:
    info = analyse.page(numero)
    aire_page = _aire(info.cropbox) if info is not None else 0.0
    part_min = corpus.seuil(SEUIL_PLEINE_PAGE)
    pleine_page: list[Aplat] = []
    partielles: list[Aplat] = []
    for aplat in analyse.aplats_de(numero):
        if not aplat.image or not aplat.opaque or not aplat.rectangulaire:
            continue
        if aire_page > 0.0 and _aire(aplat.rect) / aire_page >= part_min:
            pleine_page.append(aplat)
        else:
            partielles.append(aplat)
    images = pleine_page + partielles
    # Un recouvrement selectif laisse du texte a decouvert ; l'image d'un scan
    # ne laisse rien.
    non_couvert = any(
        not any(contient(i.rect, s.rect, _TOLERANCE) for i in images)
        for s in analyse.segments
        if s.page == numero and not s.vide and s.texte.strip()
    )
    return FaitsPage(tuple(pleine_page), tuple(partielles), non_couvert)


def faits(analyse: AnalysePdf, numero: int, corpus: Corpus) -> FaitsPage:
    """Les faits de la page, calcules une fois et gardes sur l'analyse."""
    connus = analyse.faits_scan
    if numero not in connus:
        connus[numero] = _calculer(analyse, numero, corpus)
    resultat = connus[numero]
    assert isinstance(resultat, FaitsPage)
    return resultat


def sous_image_pleine_page(analyse: AnalysePdf, segment: Segment, corpus: Corpus) -> Aplat | None:
    """L'image de page qui recouvre entierement ce segment, s'il y en a une.

    Le sens du trace ne compte pas : ce qui fait la signature d'un scan est
    qu'une image de la page entiere recouvre le texte, non l'ordre dans lequel
    le producteur les a ecrits.
    """
    for image in faits(analyse, segment.page, corpus).pleine_page:
        if contient(image.rect, segment.rect, _TOLERANCE):
            return image
    return None


def pages_comparees(contexte: Contexte) -> set[int]:
    """Les pages dont la couche invisible a ete confrontee au rendu.

    Ecrit par PDF_DIVERGENCE_RENDU, lu par PDF_RENDU_INVISIBLE : une couche
    verifiee n'a plus a etre signalee, et c'est ce qui donne au rapport un
    signal de fin. Sans cela, un appelant qui relance une analyse non confinee
    pour obtenir la comparaison ne saurait jamais qu'il l'a obtenue.
    """
    connues = contexte.cache.setdefault("pages_comparees_au_rendu", set())
    assert isinstance(connues, set)
    return connues
