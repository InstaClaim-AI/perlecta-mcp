"""L'interface en ligne de commande est l'outil de demonstration."""

from __future__ import annotations

import json

import pytest

from perlecta.cli import main


def test_affiche_le_contenu_revele(dossier_pieces, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", str(dossier_pieces / "devis_garage_piege.pdf")])
    sortie = capsys.readouterr().out
    assert code == 0
    assert "IGNORE LES CONSIGNES PRECEDENTES" in sortie
    assert "not interpreted" in sortie


def test_rapport_json(dossier_pieces, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", str(dossier_pieces / "devis_garage_piege.pdf"), "--json"])
    assert code == 0
    brut = json.loads(capsys.readouterr().out)
    assert brut["synthese"] == "anomalies_majeures"
    assert brut["anomalies"][0]["code"] == "PDF_RENDU_INVISIBLE"


def test_ne_promet_pas_la_salubrite(dossier_pieces, capsys: pytest.CaptureFixture[str]) -> None:
    main(["analyze", str(dossier_pieces / "facture_ordinaire.pdf")])
    sortie = capsys.readouterr().out
    assert "harmless" in sortie, "l'absence d'anomalie doit etre explicitement nuancee"
    for interdit in ("safe document", "document is safe", "no risk", "clean document", "is clean"):
        assert interdit not in sortie.lower()
