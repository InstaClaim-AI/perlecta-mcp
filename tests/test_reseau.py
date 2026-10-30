"""Perlecta ne fait aucune sortie reseau.

Le test coupe la fabrique de sockets et verifie qu'une analyse complete
aboutit. Il echoue si une connexion est tentee.
"""

from __future__ import annotations

import socket

import pytest

from perlecta import analyser


class TentativeDeReseau(AssertionError):
    pass


@pytest.fixture
def reseau_coupe(monkeypatch: pytest.MonkeyPatch) -> None:
    def interdit(*args: object, **kwargs: object) -> None:
        raise TentativeDeReseau("une sortie reseau a ete tentee")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)


def test_analyse_sans_reseau(dossier_pieces, reseau_coupe: None) -> None:
    rapport = analyser(dossier_pieces / "devis_garage_piege.pdf")
    assert len(rapport.anomalies) == 1
