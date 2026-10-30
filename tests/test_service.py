"""Service autonome : une API mince, sans etat, sans contenu dans les journaux."""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from perlecta.service import creer_application  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(creer_application())


def test_version(client: TestClient) -> None:
    reponse = client.get("/version")
    assert reponse.status_code == 200
    assert set(reponse.json()) == {"version_moteur", "version_corpus"}


def test_analyse_en_multipart(client: TestClient, dossier_pieces, caplog) -> None:
    octets = (dossier_pieces / "devis_garage_piege.pdf").read_bytes()
    with caplog.at_level(logging.INFO, logger="perlecta.service"):
        reponse = client.post("/analyses", files={"file": ("devis.pdf", octets, "application/pdf")})
    assert reponse.status_code == 200, reponse.text
    rapport = reponse.json()
    assert rapport["synthese"] == "anomalies_majeures"
    assert rapport["anomalies"][0]["code"] == "PDF_RENDU_INVISIBLE"
    assert "IGNORE LES CONSIGNES PRECEDENTES" in rapport["anomalies"][0]["extrait"]
    # les journaux portent l'empreinte, jamais le contenu ni le nom du fichier
    assert rapport["empreinte"] in caplog.text
    assert "IGNORE" not in caplog.text
    assert "devis.pdf" not in caplog.text


def test_plafond_de_taille_avant_analyse(client: TestClient, monkeypatch) -> None:
    from perlecta.reglage import charger

    plafond = charger().plafonds.taille_octets_max
    trop_gros = b"%PDF-1.4\n" + b"x" * plafond
    reponse = client.post("/analyses", files={"file": ("gros.pdf", trop_gros)})
    assert reponse.status_code == 413


def test_sans_etat(client: TestClient, dossier_pieces, tmp_path, monkeypatch) -> None:
    """Rien n'est ecrit par le service : le dossier courant reste vide."""
    monkeypatch.chdir(tmp_path)
    octets = (dossier_pieces / "docx_piege.docx").read_bytes()
    reponse = client.post("/analyses", files={"file": ("piece.docx", octets)})
    assert reponse.status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_pas_de_documentation_interactive(client: TestClient) -> None:
    """Pas de page de documentation chargeant des ressources distantes dans le navigateur."""
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 200
