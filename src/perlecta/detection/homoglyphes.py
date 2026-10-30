"""HOMOGLYPHES : melange de systemes d'ecriture a l'interieur d'un meme mot.

Un « е » cyrillique dans « Rеnault » se lit comme un « e » latin et ne se
cherche pas comme lui. Le systeme d'ecriture d'une lettre se lit dans son nom
Unicode, par unicodedata ; la liste des systemes, les groupes compatibles
(hiragana, katakana et sinogrammes dans un mot japonais), les lettres tolerees
(unites, symboles) et les exceptions vivent au corpus. Gravite mineure.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._texte import parties_texte, types_textuels
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "HOMOGLYPHES"
_MOT = re.compile(r"[^\W\d_]+", re.UNICODE)
_EXEMPLES_MAX = 12
_MOTS_MAX = 5000


class _Reglages:
    def __init__(self, corpus: Corpus) -> None:
        groupe = corpus.dico("homoglyphes")
        self.scripts: tuple[str, ...] = tuple(str(s) for s in groupe.get("scripts", []))
        # Les groupes compatibles qui se recoupent forment une seule famille :
        # sinogrammes, kanas et hangul ne se signalent pas entre eux.
        familles: list[set[str]] = []
        for ensemble in groupe.get("groupes_compatibles", []):
            noms = {str(s) for s in ensemble}
            fusion = {nom for f in familles if f & noms for nom in f} | noms
            familles = [f for f in familles if not (f & fusion)] + [fusion]
        self.famille: dict[str, str] = {}
        for f in familles:
            for nom in f:
                self.famille[nom] = "+".join(sorted(f))
        self.tolerees = set(str(groupe.get("lettres_tolerees", "")))
        self.exceptions = {str(e).casefold() for e in groupe.get("exceptions", [])}
        self.minimum = max(1, int(corpus.seuil("homoglyphes_mots_min")))
        self._cache: dict[str, str | None] = {}

    def script(self, lettre: str) -> str | None:
        if lettre in self._cache:
            return self._cache[lettre]
        resultat: str | None = None
        if unicodedata.category(lettre).startswith("L") and lettre not in self.tolerees:
            mots = unicodedata.name(lettre, "").split()
            for script in self.scripts:
                if script in mots:
                    resultat = self.famille.get(script, script)
                    break
        self._cache[lettre] = resultat
        return resultat


def _reglages(corpus: Corpus) -> _Reglages:
    cle = "homoglyphes.reglages"
    reglages: _Reglages | None = corpus.donnees.get(cle)
    if reglages is None:
        reglages = _Reglages(corpus)
        corpus.donnees[cle] = reglages
    return reglages


def mots_mixtes(texte: str, reglages: _Reglages) -> list[tuple[str, list[str]]]:
    """Les mots qui melangent plusieurs systemes d'ecriture, avec ces systemes."""
    resultat: list[tuple[str, list[str]]] = []
    vus: set[str] = set()
    for index, correspondance in enumerate(_MOT.finditer(texte)):
        if index >= _MOTS_MAX:
            break
        mot = correspondance.group(0)
        if len(mot) < 2 or mot in vus or mot.casefold() in reglages.exceptions:
            continue
        scripts: list[str] = []
        for lettre in mot:
            script = reglages.script(lettre)
            if script is not None and script not in scripts:
                scripts.append(script)
        if len(scripts) >= 2:
            vus.add(mot)
            resultat.append((mot, scripts))
    return resultat


class Homoglyphes:
    nom: str = CODE
    types: tuple[str, ...] = types_textuels()

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        reglages = _reglages(contexte.corpus)
        anomalies: list[Anomalie] = []
        for partie in parties_texte(contexte):
            mixtes = mots_mixtes(partie.texte, reglages)
            if len(mixtes) < reglages.minimum:
                continue
            mesure: dict[str, Any] = {
                "mots": len(mixtes),
                "exemples": [
                    {"mot": mot, "scripts": scripts} for mot, scripts in mixtes[:_EXEMPLES_MAX]
                ],
            }
            anomalies.append(
                Anomalie(
                    code=CODE,
                    gravite=contexte.corpus.gravite(CODE),
                    emplacement=Emplacement(page=partie.page, partie=partie.nom),
                    extrait=contexte.extrait(" ".join(mot for mot, _ in mixtes)),
                    mesure=mesure,
                    explication=contexte.corpus.explication(CODE),
                )
            )
            if len(anomalies) >= contexte.corpus.plafonds.anomalies_max:
                contexte.tronque = True
                break
        return anomalies


inscrire(Homoglyphes())
