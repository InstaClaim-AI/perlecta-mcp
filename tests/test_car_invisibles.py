"""CAR_INVISIBLES : caracteres sans trace a l'affichage, tous formats textuels."""

from __future__ import annotations

from perlecta import Gravite, Synthese, analyser

CODE = "CAR_INVISIBLES"


def test_revele_les_traits_conditionnels_dans_un_pdf(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "traits_conditionnels.pdf")
    anomalies = [a for a in rapport.anomalies if a.code == CODE]
    assert len(anomalies) == 1, [a.code for a in rapport.anomalies]
    anomalie = anomalies[0]
    assert anomalie.gravite is Gravite.MINEURE
    assert anomalie.emplacement.page == 1
    assert anomalie.mesure["par_classe"] == {"conditionnel": 15}
    assert anomalie.mesure["points_de_code"] == {"U+00AD": 15}
    assert "[U+00AD]" in anomalie.extrait
    assert rapport.synthese is Synthese.MINEURES
    assert CODE in rapport.detecteurs_executes


def test_revele_les_classes_dans_un_texte_brut(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "texte_piege.txt")
    assert rapport.type_detecte == "text/plain"
    anomalies = [a for a in rapport.anomalies if a.code == CODE]
    assert len(anomalies) == 1
    mesure = anomalies[0].mesure
    assert mesure["par_classe"] == {"largeur_nulle": 5, "bidirectionnel": 2, "liant": 1}
    assert mesure["total"] == 8
    assert "I[U+200B]G[U+200B]N" in anomalies[0].extrait
    assert anomalies[0].emplacement.partie == "corps"


def test_rien_sur_les_pieces_voisines(dossier_pieces) -> None:
    for nom in ("devis_garage_propre.pdf", "texte_ordinaire.txt"):
        rapport = analyser(dossier_pieces / nom)
        assert [a for a in rapport.anomalies if a.code == CODE] == [], nom


def test_la_marque_d_ordre_des_octets_n_est_pas_signalee() -> None:
    rapport = analyser("﻿Devis ordinaire\n".encode())
    assert rapport.anomalies == ()


def test_les_points_de_code_viennent_du_corpus() -> None:
    from perlecta.reglage import charger

    points = {e["de"] for e in charger().liste("caracteres_invisibles")}
    assert {"U+200B", "U+00AD", "U+202A", "U+FE00", "U+2028"} <= points
