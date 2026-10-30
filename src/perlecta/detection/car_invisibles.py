"""CAR_INVISIBLES : caracteres sans trace a l'affichage.

Espaces de largeur nulle, liants et antiliants, controles bidirectionnels,
selecteurs de variante, trait d'union conditionnel, separateurs de ligne et de
paragraphe. Ils ne se voient pas, et ils changent ce qu'un lecteur automatique
lit : un mot coupe par des caracteres de largeur nulle echappe a une recherche,
un controle bidirectionnel inverse l'ordre apparent d'un texte.

La liste des points de code vit au corpus, avec leur classe. Le detecteur
s'applique a tous les types textuels, sur le texte decode de facon fiable.
Gravite mineure : c'est un signal.
"""

from __future__ import annotations

from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._texte import PartieTexte, parties_texte, types_textuels
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "CAR_INVISIBLES"
_CONTEXTE = 24
_EXTRAITS_MAX = 4


def _point(valeur: str) -> int:
    return int(valeur.removeprefix("U+"), 16)


def _table(corpus: Corpus) -> dict[int, tuple[str, str]]:
    cle = "car_invisibles.table"
    table: dict[int, tuple[str, str]] | None = corpus.donnees.get(cle)
    if table is None:
        table = {}
        for entree in corpus.liste("caracteres_invisibles"):
            try:
                for point in range(_point(entree["de"]), _point(entree["a"]) + 1):
                    table[point] = (str(entree["classe"]), str(entree.get("libelle", "")))
            except (KeyError, ValueError, TypeError):
                continue
        corpus.donnees[cle] = table
    return table


def _notation(caractere: str) -> str:
    return f"[U+{ord(caractere):04X}]"


def reveler(texte: str, table: dict[int, tuple[str, str]]) -> str:
    """Rend visibles les caracteres invisibles d'un extrait, par leur notation."""
    return "".join(_notation(c) if ord(c) in table else c for c in texte)


def _analyser_partie(
    partie: PartieTexte, table: dict[int, tuple[str, str]]
) -> tuple[dict[str, int], dict[str, int], list[str]]:
    par_classe: dict[str, int] = {}
    par_point: dict[str, int] = {}
    extraits: list[str] = []
    dernier_extrait = -1
    for index, caractere in enumerate(partie.texte):
        entree = table.get(ord(caractere))
        if entree is None:
            continue
        classe = entree[0]
        par_classe[classe] = par_classe.get(classe, 0) + 1
        notation = f"U+{ord(caractere):04X}"
        par_point[notation] = par_point.get(notation, 0) + 1
        if len(extraits) < _EXTRAITS_MAX and index > dernier_extrait:
            debut, fin = max(0, index - _CONTEXTE), min(len(partie.texte), index + _CONTEXTE)
            extraits.append(reveler(partie.texte[debut:fin], table).replace("\n", " "))
            dernier_extrait = fin
    return par_classe, par_point, extraits


class CaracteresInvisibles:
    nom: str = CODE
    types: tuple[str, ...] = types_textuels()

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        table = _table(contexte.corpus)
        minimum = int(contexte.corpus.seuil("caracteres_invisibles_min"))
        anomalies: list[Anomalie] = []
        for partie in parties_texte(contexte):
            par_classe, par_point, extraits = _analyser_partie(partie, table)
            total = sum(par_classe.values())
            if total < max(1, minimum):
                continue
            mesure: dict[str, Any] = {
                "total": total,
                "par_classe": par_classe,
                "points_de_code": par_point,
            }
            anomalies.append(
                Anomalie(
                    code=CODE,
                    gravite=contexte.corpus.gravite(CODE),
                    emplacement=Emplacement(page=partie.page, partie=partie.nom),
                    extrait=contexte.extrait(" … ".join(extraits)),
                    mesure=mesure,
                    explication=contexte.corpus.explication(CODE),
                )
            )
            if len(anomalies) >= contexte.corpus.plafonds.anomalies_max:
                contexte.tronque = True
                break
        return anomalies


inscrire(CaracteresInvisibles())
