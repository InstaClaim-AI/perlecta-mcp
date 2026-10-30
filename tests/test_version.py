"""La version du moteur rapportee est celle du paquet installe."""

from __future__ import annotations

from importlib.metadata import version

from perlecta import VERSION_MOTEUR, __version__


def test_version_coherente() -> None:
    assert __version__ == VERSION_MOTEUR == version("perlecta")


def test_le_moteur_n_importe_que_la_bibliotheque_standard_et_pikepdf() -> None:
    """D1 : aucune dependance montante, aucune dependance d'analyse autre que pikepdf.

    Les extras (service, rendu, mcp) ne sont importes que par leurs modules dedies,
    jamais par le moteur, et toujours sous garde d'ImportError.
    """
    import ast
    import sys
    from pathlib import Path

    racine = Path(__file__).resolve().parents[1] / "src" / "perlecta"
    standard = set(sys.stdlib_module_names)
    autorises = standard | {"perlecta", "pikepdf"}
    extras = {"fastapi", "uvicorn", "pymupdf", "pytesseract", "PIL"}
    for fichier in racine.rglob("*.py"):
        if fichier.name in {"service.py", "serveur_mcp.py"}:
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            noms: list[str] = []
            if isinstance(noeud, ast.Import):
                noms = [a.name.split(".")[0] for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                noms = [noeud.module.split(".")[0]]
            for nom in noms:
                assert nom in autorises or nom in extras, f"{fichier.name} importe {nom}"
