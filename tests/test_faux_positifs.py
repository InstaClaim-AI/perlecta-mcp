"""Absence de faux positifs sur des documents ordinaires.

C'est ce qui decide si le produit est utilisable en production ou s'il crie au
loup. Le texte blanc sur bandeau colore et le filigrane gris clair sont les
deux pieges classiques.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest

from perlecta import Rapport, Synthese, analyser
from tests.fixtures.generer import ORDINAIRES


@cache
def _rapport(chemin: Path) -> Rapport:
    """Chaque piece est analysee une fois : le rendu optique est couteux."""
    return analyser(chemin)


# Chaque detecteur livre declare ici les codes qu'il peut emettre. Deux
# verifications en decoulent : la liste des detecteurs est comparee au registre,
# donc un detecteur inscrit mais absent d'ici fait echouer la suite ; et chaque
# code est verifie absent des pieces de reference. Un detecteur peut porter
# plusieurs codes quand il distingue des gravites.
CODES_PAR_DETECTEUR = {
    "PDF_RENDU_INVISIBLE": ("PDF_RENDU_INVISIBLE", "PDF_COUCHE_NUMERISEE"),
    "PDF_COULEUR_FOND": ("PDF_COULEUR_FOND",),
    "PDF_TAILLE_NULLE": ("PDF_TAILLE_NULLE",),
    "PDF_HORS_PAGE": ("PDF_HORS_PAGE",),
    "PDF_ACTION": ("PDF_ACTION_AUTOMATIQUE", "PDF_LIEN_CLIQUABLE"),
    "CAR_INVISIBLES": ("CAR_INVISIBLES",),
    "META_INSTRUCTION": ("META_INSTRUCTION",),
    "PDF_CALQUE_MASQUE": ("PDF_CALQUE_MASQUE",),
    "HOMOGLYPHES": ("HOMOGLYPHES",),
    "DOCX_TEXTE_MASQUE": ("DOCX_TEXTE_MASQUE",),
    "EML_CONTENU_MASQUE": ("EML_CONTENU_MASQUE",),
    "PDF_OCCULTATION": ("PDF_OCCULTATION",),
    "PDF_DIVERGENCE_RENDU": ("PDF_DIVERGENCE_RENDU",),
}

# Couples (detecteur, code) a verifier : le detecteur doit avoir tourne, le code
# ne doit pas apparaitre.
COUPLES = tuple(
    (detecteur, code) for detecteur, codes in sorted(CODES_PAR_DETECTEUR.items()) for code in codes
)

# Les quatre pieces de reference, qui doivent rester sans anomalie quoi qu'il
# arrive, puis les pieces ordinaires ajoutees au fil des detecteurs.
REFERENCE = (
    "devis_garage_propre.pdf",
    "filigrane_legitime.pdf",
    "blanc_sur_fond_colore.pdf",
    "facture_ordinaire.pdf",
)


def test_tout_detecteur_inscrit_est_verifie() -> None:
    from perlecta.detection import registre

    assert {d.nom for d in registre()} == set(CODES_PAR_DETECTEUR)


@pytest.mark.parametrize("nom", sorted(set(REFERENCE) | set(ORDINAIRES)))
def test_aucune_anomalie_sur_piece_ordinaire(dossier_pieces, nom: str) -> None:
    rapport = _rapport(dossier_pieces / nom)
    assert rapport.anomalies == (), (
        f"faux positif sur {nom} : {[a.code for a in rapport.anomalies]}"
    )
    assert rapport.synthese is Synthese.AUCUNE
    assert not rapport.tronque


@pytest.mark.parametrize(("detecteur", "code"), COUPLES)
@pytest.mark.parametrize("nom", REFERENCE)
def test_code_absent_des_pieces_de_reference(
    dossier_pieces, detecteur: str, code: str, nom: str
) -> None:
    """Le detecteur a tourne sans rien trouver, ou a ete ecarte pour le type seulement."""
    rapport = _rapport(dossier_pieces / nom)
    ecarte_pour_le_type = any(
        i.nom == detecteur and i.motif.startswith("type non pris en charge")
        for i in rapport.detecteurs_ignores
    )
    dependance_absente = any(
        i.nom == detecteur and ("absent" in i.motif) for i in rapport.detecteurs_ignores
    )
    assert detecteur in rapport.detecteurs_executes or ecarte_pour_le_type or dependance_absente, (
        f"{detecteur} n'a pas tourne sur {nom}"
    )
    assert [a for a in rapport.anomalies if a.code == code] == []
