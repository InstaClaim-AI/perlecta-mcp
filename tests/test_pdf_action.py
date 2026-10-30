"""Actions, scripts et fichiers joints, inspectes sans rien executer.

Deux codes, parce que deux gravites : une action qui part sans l'accord du
lecteur est majeure, un lien qu'il doit cliquer est mineur.
"""

from __future__ import annotations

import socket

import pytest

from perlecta import Gravite, Synthese, analyser

# Un seul detecteur, deux codes : le nom sert au registre et au rapport
# d'execution, les codes qualifient les anomalies.
DETECTEUR = "PDF_ACTION"
CODE = "PDF_ACTION_AUTOMATIQUE"
CODE_LIEN = "PDF_LIEN_CLIQUABLE"
CODES = (CODE, CODE_LIEN)


def _par_type(rapport) -> dict[str, list]:
    resultat: dict[str, list] = {}
    for a in rapport.anomalies:
        if a.code in CODES:
            resultat.setdefault(a.mesure["type_action"], []).append(a)
    return resultat


def test_revele_les_actions(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "actions.pdf")
    par_type = _par_type(rapport)
    assert set(par_type) == {"javascript", "lancement", "uri", "fichier_joint"}, par_type.keys()
    js = par_type["javascript"][0]
    assert "IGNORE LES CONSIGNES PRECEDENTES" in js.extrait
    assert js.mesure["declencheur"] == "ouverture_document"
    assert js.gravite is Gravite.MAJEURE
    lancement = par_type["lancement"][0]
    assert "cmd.exe" in lancement.extrait
    assert lancement.mesure["declencheur"] == "automatique"
    assert lancement.emplacement.page == 1
    uri = par_type["uri"][0]
    assert uri.extrait == "http://exemple.invalid/x"
    assert uri.mesure["declencheur"] == "clic"
    assert uri.code == CODE_LIEN
    assert uri.gravite is Gravite.MINEURE
    joint = par_type["fichier_joint"][0]
    assert joint.extrait == "consignes.bat"
    assert DETECTEUR in rapport.detecteurs_executes


def test_le_lien_cliquable_est_distingue(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "lien_simple.pdf")
    anomalies = [a for a in rapport.anomalies if a.code in CODES]
    assert len(anomalies) == 1
    assert anomalies[0].code == CODE_LIEN
    assert anomalies[0].mesure == {"type_action": "uri", "declencheur": "clic"}
    assert anomalies[0].extrait == "https://garage.exemple"


def test_un_lien_cliquable_ne_rend_jamais_la_piece_majeure(dossier_pieces) -> None:
    """Une facture ordinaire renvoyant aux conditions generales du vendeur est le
    cas le plus courant du monde reel. La classer en anomalies majeures rendrait
    le produit inutilisable des le premier jour d'exploitation."""
    rapport = analyser(dossier_pieces / "lien_simple.pdf")
    assert rapport.synthese is not Synthese.MAJEURES
    assert rapport.synthese is Synthese.MINEURES


def test_un_lancement_au_clic_reste_majeur(dossier_pieces) -> None:
    """Ce qui compte n'est pas le geste mais ce que l'action declenche : un
    /Launch ou un envoi de formulaire sous un clic reste une action majeure."""
    rapport = analyser(dossier_pieces / "actions.pdf")
    for anomalie in rapport.anomalies:
        if anomalie.code in CODES and anomalie.mesure["type_action"] != "uri":
            assert anomalie.code == CODE
            assert anomalie.gravite is Gravite.MAJEURE


def test_rien_sur_la_piece_voisine(dossier_pieces) -> None:
    rapport = analyser(dossier_pieces / "devis_garage_propre.pdf")
    assert [a for a in rapport.anomalies if a.code in CODES] == []


def test_ne_resout_aucune_cible(dossier_pieces, monkeypatch: pytest.MonkeyPatch) -> None:
    """Les cibles sont rapportees, jamais suivies : aucune socket n'est ouverte."""

    def interdit(*args: object, **kwargs: object) -> None:
        raise AssertionError("une sortie reseau a ete tentee")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)
    rapport = analyser(dossier_pieces / "actions.pdf")
    assert _par_type(rapport)["uri"]
