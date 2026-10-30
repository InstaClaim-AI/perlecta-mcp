"""PDF_RENDU_INVISIBLE : texte place en mode de rendu invisible.

Le mode de rendu de texte est fixe par l'operateur Tr. Les modes 3 et 7 ne
dessinent ni le remplissage ni le contour : le texte est present dans le
fichier, extractible par n'importe quel outil, et absent de l'affichage comme
de l'impression. C'est le procede le plus repandu, et le moins couteux a
detecter : il se lit dans l'etat graphique, sans calcul de couleur ni de
geometrie.

Le mode fait partie de l'etat graphique : il est empile par q et restaure par
Q, et il survit a BT/ET. L'interprete partage le tient ainsi.

Un cas est ecarte : la couche texte d'un document numerise, invisible sous
l'image de la page. C'est le procede normal d'un scanner, et le signaler
reviendrait a declarer majeure la quasi-totalite des pieces recues. Le segment
est alors laisse a la comparaison au rendu, qui verifie qu'il dit bien ce que
l'image montre. Voir _scan.py.
"""

from __future__ import annotations

from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._pdf import (
    AnalysePdf,
    Segment,
    _arrondir,
    analyse_pdf,
    anomalies_par_ligne,
    inscrire_predicat,
    regrouper,
    segments_attribues,
    texte_du_groupe,
    union,
)
from perlecta.detection._scan import pages_comparees, sous_image_pleine_page
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "PDF_RENDU_INVISIBLE"
CODE_COUCHE = "PDF_COUCHE_NUMERISEE"


def _predicat(analyse: AnalysePdf, segment: Segment, corpus: Corpus) -> dict[str, Any] | None:
    if not segment.invisible_par_rendu:
        return None
    if sous_image_pleine_page(analyse, segment, corpus) is not None:
        # Couche de reconnaissance optique sous l'image de la page : c'est ainsi
        # que tout scanner rend un document cherchable. Le segment n'est
        # attribue a personne, pour que la comparaison au rendu le reprenne, et
        # il ressort en mineure sous CODE_COUCHE : l'ecart n'est jamais muet.
        return None
    mesure: dict[str, Any] = {"mode_rendu": segment.mode_rendu}
    mesure["x"], mesure["y"] = round(segment.rect[0], 2), round(segment.rect[1], 2)
    return mesure


def _couches(contexte: Contexte) -> list[Anomalie]:
    """Une anomalie mineure par page portant une couche non verifiee.

    Le texte ecarte par le predicat est rapporte ici. Une page numerisee en
    produit une seule, et non une par ligne : c'est un etat de la page, pas une
    liste de dissimulations.

    Une page que la comparaison au rendu a confrontee a son image n'en produit
    aucune : la couche y est verifiee. C'est ce qui permet a un appelant de
    savoir si une seconde analyse, non confinee, lui a apporte la verification
    qui manquait.
    """
    analyse = analyse_pdf(contexte)
    corpus = contexte.corpus
    verifiees = pages_comparees(contexte)
    par_page: dict[int, list[Segment]] = {}
    for segment in analyse.segments:
        if segment.page in verifiees:
            continue
        if not segment.invisible_par_rendu or segment.vide:
            continue
        if not segment.texte.strip() and segment.decodage != "inconnu":
            continue
        if sous_image_pleine_page(analyse, segment, corpus) is None:
            continue
        par_page.setdefault(segment.page, []).append(segment)

    anomalies: list[Anomalie] = []
    for page in sorted(par_page):
        segments = par_page[page]
        texte = " ".join(texte_du_groupe(g).strip() for g in regrouper(segments)).strip()
        anomalies.append(
            Anomalie(
                code=CODE_COUCHE,
                gravite=corpus.gravite(CODE_COUCHE),
                emplacement=Emplacement(
                    page=page,
                    rectangle=_arrondir(union(s.rect for s in segments)),
                    position_flux=segments[0].position_flux,
                ),
                extrait=contexte.extrait(texte),
                mesure={
                    "mode_rendu": segments[0].mode_rendu,
                    "segments": len(segments),
                    "verifiee_par_le_rendu": False,
                },
                explication=corpus.explication(CODE_COUCHE),
            )
        )
    return anomalies


class RenduInvisible:
    nom: str = CODE
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        retenus = [
            (segment, mesure)
            for segment, mesure in segments_attribues(contexte, CODE)
            if segment.texte.strip() or segment.decodage == "inconnu"
        ]
        return anomalies_par_ligne(contexte, CODE, retenus) + _couches(contexte)


inscrire_predicat(CODE, _predicat)
inscrire(RenduInvisible())
