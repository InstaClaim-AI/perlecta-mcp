"""HOMOGLYPHES : melange de systemes d'ecriture dans un meme mot."""

from __future__ import annotations

from perlecta import Gravite, Synthese, analyser

CODE = "HOMOGLYPHES"


def test_revele_les_lettres_cyrilliques_dans_un_texte(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "homoglyphes.txt")
    anomalies = [a for a in rapport.anomalies if a.code == CODE]
    assert len(anomalies) == 1, [a.code for a in rapport.anomalies]
    anomalie = anomalies[0]
    assert anomalie.gravite is Gravite.MINEURE
    assert anomalie.mesure["mots"] == 4
    mots = {e["mot"]: e["scripts"] for e in anomalie.mesure["exemples"]}
    assert mots["Rеnault"] == ["LATIN", "CYRILLIC"]
    assert "Gаrage" in mots
    assert "Rеnault" in anomalie.extrait
    assert rapport.synthese is Synthese.MINEURES


def test_revele_la_table_tounicode_piegee_d_un_pdf(dossier_pieces) -> None:
    """L'affichage montre « Renault », le texte extrait porte un е cyrillique."""
    rapport = analyser(dossier_pieces / "homoglyphes.pdf")
    anomalies = [a for a in rapport.anomalies if a.code == CODE]
    assert len(anomalies) == 1, [a.code for a in rapport.anomalies]
    assert anomalies[0].emplacement.page == 1
    assert anomalies[0].mesure["mots"] >= 5
    assert "Pеinturе" in anomalies[0].extrait
    assert [a.code for a in rapport.anomalies] == [CODE]
    assert CODE in rapport.detecteurs_executes


def test_rien_sur_les_pieces_voisines(dossier_pieces) -> None:
    for nom in ("devis_garage_propre.pdf", "texte_ordinaire.txt"):
        rapport = analyser(dossier_pieces / nom)
        assert [a for a in rapport.anomalies if a.code == CODE] == [], nom


def test_tolere_les_unites_et_les_symboles(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "unites_et_symboles.txt")
    assert rapport.anomalies == ()


def test_tolere_un_mot_japonais() -> None:
    rapport = analyser("見積もり カタカナ 漢字 mélange\n".encode())
    assert rapport.anomalies == ()


def test_les_reglages_viennent_du_corpus() -> None:
    from perlecta.reglage import charger

    groupe = charger().dico("homoglyphes")
    assert "CYRILLIC" in groupe["scripts"]
    assert "µm" in groupe["exceptions"]
