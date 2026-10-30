from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from tests.fixtures.generer import DOSSIER, ORDINAIRES, generer  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def pieces() -> None:
    """Les fixtures sont produites par leur script, jamais versionnees en binaire."""
    generer()


@pytest.fixture
def dossier_pieces() -> Path:
    return DOSSIER


@pytest.fixture
def pieces_ordinaires() -> tuple[str, ...]:
    return ORDINAIRES
