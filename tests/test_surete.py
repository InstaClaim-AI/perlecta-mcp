"""Surete d'execution : un document degrade tronque et rapporte, il ne fait rien tomber."""

from __future__ import annotations

import pytest

from perlecta import analyser
from perlecta.moteur import _lire


@pytest.mark.parametrize("nom", ["tronque.pdf", "faux_type.pdf"])
def test_document_degrade_ne_leve_pas(dossier_pieces, nom: str) -> None:
    rapport = analyser(dossier_pieces / nom)
    assert rapport.anomalies == ()
    assert rapport.detecteurs_ignores, "un detecteur non execute doit etre declare avec son motif"
    for ignore in rapport.detecteurs_ignores:
        assert ignore.motif, "un motif vide masquerait la portee reelle de l'analyse"


def test_lecture_plafonnee() -> None:
    octets, tronque = _lire(b"x" * 5000, 1000)
    assert len(octets) == 1000
    assert tronque is True


def test_lecture_sous_le_plafond() -> None:
    octets, tronque = _lire(b"x" * 500, 1000)
    assert len(octets) == 500
    assert tronque is False


def test_document_vide(dossier_pieces) -> None:
    rapport = analyser(b"")
    assert rapport.taille_octets == 0
    assert rapport.anomalies == ()
    assert rapport.empreinte == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_extrait_plafonne(dossier_pieces) -> None:
    from perlecta.detection.base import Contexte
    from perlecta.reglage import charger

    corpus = charger()
    contexte = Contexte(octets=b"", type_detecte="application/pdf", corpus=corpus)
    long = "a" * (corpus.plafonds.extrait_caracteres_max + 100)
    assert len(contexte.extrait(long)) == corpus.plafonds.extrait_caracteres_max
    assert contexte.tronque is True


def test_archive_expansive_tronque_et_rapporte(dossier_pieces) -> None:
    """Une archive a fort taux d'expansion n'est pas lue au-dela du plafond."""
    rapport = analyser(dossier_pieces / "archive_expansive.docx")
    assert rapport.type_detecte == "application/zip"
    assert rapport.tronque is True
    assert rapport.anomalies == ()
    motifs = {i.nom: i.motif for i in rapport.detecteurs_ignores}
    assert "expansion" in motifs["DOCX_TEXTE_MASQUE"]


def test_chemin_traversant_refuse(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "chemin_traversant.docx")
    assert rapport.anomalies == ()
    motifs = {i.nom: i.motif for i in rapport.detecteurs_ignores}
    assert "traversant" in motifs["DOCX_TEXTE_MASQUE"]


def test_archive_sans_document_word() -> None:
    import io
    import zipfile

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("notes.txt", "rien")
    rapport = analyser(tampon.getvalue())
    assert rapport.anomalies == ()
    motifs = {i.nom: i.motif for i in rapport.detecteurs_ignores}
    assert "pas un document Word" in motifs["DOCX_TEXTE_MASQUE"]
