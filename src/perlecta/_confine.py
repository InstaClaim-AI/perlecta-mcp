"""Processus fils d'une analyse confinee.

Pose ses propres limites de ressources avant d'importer quoi que ce soit de
lourd, lit le document sur l'entree standard, ecrit le rapport en JSON sur la
sortie standard.
"""

from __future__ import annotations

import json
import os
import resource
import sys


def _poser(nom: str, valeur: int) -> bool:
    """Pose une limite ; rend faux si l'hote la refuse ou ne la connait pas."""
    limite = getattr(resource, nom, None)
    if limite is None:
        return False
    try:
        resource.setrlimit(limite, (valeur, valeur))
    except (ValueError, OSError):
        return False
    return True


def _poser_limites(memoire_octets: int, duree_s: int) -> list[str]:
    """Pose les limites et rend le nom de celles que l'hote a refusees.

    Linux accepte RLIMIT_AS. macOS refuse toute limite de memoire finie
    (RLIMIT_AS, RLIMIT_DATA, RLIMIT_RSS) : le plafond de memoire y releve du
    conteneur, et le refus est signale sur la sortie d'erreur plutot que de
    faire echouer l'analyse, qui rendrait alors un rapport degrade pour un
    motif etranger au document.
    """
    refusees: list[str] = []
    if not _poser("RLIMIT_AS", memoire_octets) and not _poser("RLIMIT_DATA", memoire_octets):
        refusees.append("memoire")
    for nom, valeur in (
        ("RLIMIT_CPU", duree_s),
        ("RLIMIT_NOFILE", 64),
        ("RLIMIT_FSIZE", 0),
        ("RLIMIT_CORE", 0),
    ):
        if not _poser(nom, valeur):
            refusees.append(nom)
    # Pas de RLIMIT_NPROC : la limite compte les processus et les fils de
    # l'utilisateur, pas ceux de ce processus. Toute valeur basse echoue des que
    # l'hote en execute davantage, et zero tue le processus lui-meme. Le
    # plafonnement du nombre de processus releve du conteneur, pas d'ici.
    return refusees


def main() -> int:
    memoire = int(os.environ.get("PERLECTA_MEMOIRE_MAX", 1 << 30))
    duree = int(os.environ.get("PERLECTA_DUREE_MAX_S", 30))
    version_corpus = os.environ.get("PERLECTA_CORPUS", "v1")
    type_mime = os.environ.get("PERLECTA_TYPE") or None

    for nom in _poser_limites(memoire, duree):
        sys.stderr.write(f"limite non appliquee par l'hote : {nom}\n")

    octets = sys.stdin.buffer.read()

    from perlecta.moteur import analyser

    rapport = analyser(octets, type_mime=type_mime, version_corpus=version_corpus)
    # ASCII seul : aucun octet du document ne peut rendre la sortie illisible au parent
    sys.stdout.write(json.dumps(rapport.en_dict(), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
