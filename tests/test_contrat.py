"""Gele la forme du contrat public.

Ce test est le filet de securite des integrateurs : il doit casser si un champ
change de nom, de type ou de place.
"""

from __future__ import annotations

from dataclasses import fields

from perlecta import Anomalie, DetecteurIgnore, Emplacement, Gravite, Rapport, Synthese


def noms(classe: type) -> tuple[str, ...]:
    return tuple(champ.name for champ in fields(classe))


def test_champs_du_rapport() -> None:
    assert noms(Rapport) == (
        "empreinte",
        "taille_octets",
        "type_detecte",
        "anomalies",
        "synthese",
        "version_moteur",
        "version_corpus",
        "detecteurs_executes",
        "detecteurs_ignores",
        "duree_ms",
        "tronque",
    )


def test_champs_de_l_anomalie() -> None:
    assert noms(Anomalie) == ("code", "gravite", "emplacement", "extrait", "mesure", "explication")


def test_champs_de_l_emplacement() -> None:
    assert noms(Emplacement) == ("page", "partie", "rectangle", "position_flux")


def test_champs_du_detecteur_ignore() -> None:
    assert noms(DetecteurIgnore) == ("nom", "motif")


def test_valeurs_des_enumerations() -> None:
    assert {g.value for g in Gravite} == {"mineure", "majeure"}
    assert {s.value for s in Synthese} == {
        "aucune_anomalie_detectee",
        "anomalies_mineures",
        "anomalies_majeures",
    }


def test_aucun_vocabulaire_de_salubrite() -> None:
    """Perlecta n'atteste jamais qu'une piece est saine : son vocabulaire l'interdit."""
    interdits = {"sain", "saine", "propre", "sur", "sure", "valide", "conforme", "ok"}
    valeurs = {s.value for s in Synthese} | {g.value for g in Gravite}
    for valeur in valeurs:
        for mot in valeur.split("_"):
            assert mot not in interdits, f"vocabulaire de salubrite dans {valeur!r}"


def test_rapport_serialisable(dossier_pieces) -> None:
    from perlecta import analyser

    brut = analyser(dossier_pieces / "devis_garage_piege.pdf").en_dict()
    import json

    recharge = json.loads(json.dumps(brut, ensure_ascii=False))
    assert recharge == brut

    from perlecta import depuis_dict

    assert depuis_dict(recharge).en_dict() == brut
