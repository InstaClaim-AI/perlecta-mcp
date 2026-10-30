"""META_INSTRUCTION : metadonnees imperatives, reconnues par motifs du corpus."""

from __future__ import annotations

from perlecta import Gravite, Synthese, analyser

CODE = "META_INSTRUCTION"


def test_revele_les_metadonnees_imperatives(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "metadonnees_piegees.pdf")
    anomalies = {a.mesure["champ"]: a for a in rapport.anomalies if a.code == CODE}
    assert {"Subject", "Keywords", "description"} <= set(anomalies), anomalies.keys()
    sujet = anomalies["Subject"]
    assert sujet.gravite is Gravite.MINEURE
    assert sujet.emplacement.partie == "Info"
    assert "Ignore les consignes" in sujet.extrait
    assert "demande d'ignorer des consignes" in sujet.mesure["motifs"]
    assert "injonction de qualification" in sujet.mesure["motifs"]
    assert "injonction a la deuxieme personne" in anomalies["Keywords"].mesure["motifs"]
    assert anomalies["description"].emplacement.partie == "XMP"
    assert "demande d'adopter un role" in anomalies["description"].mesure["motifs"]
    assert rapport.synthese is Synthese.MINEURES
    assert CODE in rapport.detecteurs_executes


def test_rien_sur_la_piece_voisine(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "metadonnees_ordinaires.pdf")
    assert [a for a in rapport.anomalies if a.code == CODE] == []
    assert rapport.anomalies == ()


def test_les_motifs_viennent_du_corpus_et_compilent() -> None:
    import re

    from perlecta.reglage import charger

    motifs = charger().liste("motifs_instruction")
    assert len(motifs) >= 6
    for entree in motifs:
        re.compile(entree["motif"])
        assert entree["libelle"]
