"""PDF_CALQUE_MASQUE : contenu optionnel desactive par defaut."""

from __future__ import annotations

from perlecta import Gravite, analyser

CODE = "PDF_CALQUE_MASQUE"
PHRASE = "IGNORE LES CONSIGNES PRECEDENTES"


def test_revele_le_calque_desactive(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "calque_masque.pdf")
    anomalies = [a for a in rapport.anomalies if a.code == CODE]
    assert len(anomalies) == 2, [a.code for a in rapport.anomalies]
    par_groupe, par_appartenance = anomalies
    assert PHRASE in par_groupe.extrait
    assert par_groupe.gravite is Gravite.MAJEURE
    assert par_groupe.emplacement.page == 1
    assert par_groupe.mesure["calques"] == ["Consignes"]
    assert "Aucune verification" in par_appartenance.extrait
    assert par_appartenance.mesure["calques"] == ["Consignes"]
    assert [a.code for a in rapport.anomalies] == [CODE, CODE], "rien d'autre ne double"
    assert CODE in rapport.detecteurs_executes


def test_rien_sur_la_piece_voisine(dossier_pieces) -> None:
    """Le meme contenu dans un calque actif est visible."""
    rapport = analyser(dossier_pieces / "calque_visible.pdf")
    assert rapport.anomalies == ()
