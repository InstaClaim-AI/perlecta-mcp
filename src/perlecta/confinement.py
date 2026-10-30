"""Analyse confinee : l'appel que les integrateurs doivent utiliser.

Perlecta lit des documents choisis par un attaquant. Les bibliotheques
d'analyse de documents sont une source classique de debordements, de boucles
non bornees et d'epuisement memoire. L'analyse tourne donc dans un
sous-processus avec limites de ressources, sans environnement herite, sans
droit d'ecriture et sans creation de processus.

Ce n'est pas un service web : c'est un bac a sable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from perlecta.contrat import (
    Anomalie,
    DetecteurIgnore,
    Emplacement,
    Gravite,
    Rapport,
    Synthese,
)
from perlecta.moteur import VERSION_MOTEUR, Source, _lire
from perlecta.reglage import CORPUS_DEFAUT, charger

MARGE_DUREE_S = 10


class EchecConfinement(RuntimeError):
    """Le sous-processus n'a pas rendu de rapport exploitable."""


def analyser_confine(
    source: Source,
    type_mime: str | None = None,
    version_corpus: str = CORPUS_DEFAUT,
) -> Rapport:
    corpus = charger(version_corpus)
    octets, _ = _lire(source, corpus.plafonds.taille_octets_max)

    duree_s = corpus.plafonds.duree_ms_max // 1000 + MARGE_DUREE_S
    environnement = {
        "PATH": "/usr/bin:/bin",
        "PERLECTA_MEMOIRE_MAX": str(corpus.plafonds.memoire_octets_max),
        "PERLECTA_DUREE_MAX_S": str(duree_s),
        "PERLECTA_CORPUS": version_corpus,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if type_mime:
        environnement["PERLECTA_TYPE"] = type_mime

    try:
        acheve = subprocess.run(
            [sys.executable, "-s", "-B", "-m", "perlecta._confine"],
            input=octets,
            capture_output=True,
            env=environnement,
            timeout=duree_s + MARGE_DUREE_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _rapport_degrade(octets, type_mime, corpus.version, "plafond de duree depasse")

    if acheve.returncode != 0 or not acheve.stdout:
        motif = _motif(acheve.returncode, acheve.stderr)
        return _rapport_degrade(octets, type_mime, corpus.version, motif)

    try:
        return depuis_dict(json.loads(acheve.stdout))
    except (ValueError, KeyError) as err:
        raise EchecConfinement(f"rapport illisible : {err}") from err


def _motif(code_retour: int, erreur: bytes) -> str:
    if code_retour < 0:
        return f"processus interrompu par le signal {-code_retour}"
    extrait = erreur.decode("utf-8", errors="replace").strip().splitlines()
    dernier = extrait[-1] if extrait else "sans message"
    return f"echec du sous-processus ({code_retour}) : {dernier[:200]}"


def _rapport_degrade(
    octets: bytes, type_mime: str | None, version_corpus: str, motif: str
) -> Rapport:
    """Une analyse qui echoue rend un rapport qui le dit, jamais un silence."""
    import hashlib

    from perlecta.typage import detecter

    return Rapport(
        empreinte=hashlib.sha256(octets).hexdigest(),
        taille_octets=len(octets),
        type_detecte=type_mime or detecter(octets),
        anomalies=(),
        synthese=Synthese.AUCUNE,
        version_moteur=VERSION_MOTEUR,
        version_corpus=version_corpus,
        detecteurs_executes=(),
        detecteurs_ignores=(DetecteurIgnore("*", motif),),
        duree_ms=0,
        tronque=True,
    )


def _rectangle(valeur: Any) -> tuple[float, float, float, float] | None:
    if not valeur:
        return None
    x0, y0, x1, y1 = (float(v) for v in valeur)
    return (x0, y0, x1, y1)


def depuis_dict(brut: dict[str, Any]) -> Rapport:
    """Reconstruit un Rapport depuis sa forme JSON. Utile aux integrateurs."""
    anomalies = tuple(
        Anomalie(
            code=a["code"],
            gravite=Gravite(a["gravite"]),
            emplacement=Emplacement(
                page=a["emplacement"].get("page"),
                partie=a["emplacement"].get("partie"),
                rectangle=_rectangle(a["emplacement"].get("rectangle")),
                position_flux=a["emplacement"].get("position_flux"),
            ),
            extrait=a["extrait"],
            mesure=a.get("mesure", {}),
            explication=a.get("explication", ""),
        )
        for a in brut["anomalies"]
    )
    return Rapport(
        empreinte=brut["empreinte"],
        taille_octets=brut["taille_octets"],
        type_detecte=brut["type_detecte"],
        anomalies=anomalies,
        synthese=Synthese(brut["synthese"]),
        version_moteur=brut["version_moteur"],
        version_corpus=brut["version_corpus"],
        detecteurs_executes=tuple(brut["detecteurs_executes"]),
        detecteurs_ignores=tuple(
            DetecteurIgnore(d["nom"], d["motif"]) for d in brut["detecteurs_ignores"]
        ),
        duree_ms=brut["duree_ms"],
        tronque=brut["tronque"],
    )
