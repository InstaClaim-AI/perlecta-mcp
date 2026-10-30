"""DOCX_TEXTE_MASQUE : texte present dans un document Word mais non affiche.

Procedes reconnus, chacun rapporte dans la mesure :
- vanish, web_hidden : propriete de masquage du passage ;
- couleur_fond : couleur de police indiscernable du fond effectif (trame du
  passage, trame du paragraphe, fond du document, blanc par defaut) ;
- taille : taille de police sous le seuil du corpus ;
- revision_supprimee : texte supprime dont la revision n'est pas acceptee ;
- code_champ : instruction de champ portant du texte libre, jamais affichee ;
- commentaire : texte des commentaires, hors du corps imprime.

Les codes de champ ordinaires (PAGE, TOC, HYPERLINK…) sont reconnus par la
liste du corpus et ne sont pas signales.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._docx import _PARTIES_TEXTE, balise, lire_docx, texte_de
from perlecta.detection._pdf import Couleur, distance
from perlecta.detection.base import Contexte, inscrire
from perlecta.reglage import Corpus

CODE = "DOCX_TEXTE_MASQUE"
_FAUX = {"0", "false", "off"}
_HEX = re.compile(r"^[0-9A-Fa-f]{6}$")
_COMMUTATEUR = re.compile(r"\\\S*")
_GUILLEMETS = re.compile(r'"[^"]*"|“[^”]*”')


def _val(element: Element | None, attribut: str = "val") -> str | None:
    if element is None:
        return None
    return element.get(f"{{{balise('')[1:-1]}}}{attribut}") or element.get(attribut)


def _actif(element: Element | None) -> bool:
    if element is None:
        return False
    valeur = _val(element)
    return valeur is None or valeur.lower() not in _FAUX


def _couleur(valeur: str | None) -> Couleur | None:
    if valeur is None or not _HEX.match(valeur):
        return None
    return tuple(int(valeur[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _champ_libre(instruction: str, connus: set[str], minimum: int) -> str | None:
    """Le texte libre d'une instruction de champ, s'il depasse le minimum de mots."""
    texte = instruction.strip()
    if not texte:
        return None
    mots = texte.split()
    if mots and mots[0].upper() in connus:
        texte = texte[len(mots[0]) :]
    texte = _COMMUTATEUR.sub(" ", texte)
    cites = _GUILLEMETS.findall(texte)
    restant = _GUILLEMETS.sub(" ", texte)
    libres = [m for m in restant.split() if len(m) > 1 and not m.startswith("http")]
    for cite in cites:
        libres.extend(m for m in cite.strip('"“”').split() if not m.startswith("http"))
    if len(libres) < minimum:
        return None
    return instruction.strip()


class _Analyse:
    def __init__(self, contexte: Contexte) -> None:
        self.contexte = contexte
        corpus: Corpus = contexte.corpus
        self.seuil_couleur = corpus.seuil("distance_couleur_fond_max")
        self.taille_min = corpus.seuil("taille_police_min")
        self.mots_min = max(1, int(corpus.seuil("code_champ_mots_min")))
        self.connus = {str(c).upper() for c in corpus.liste("champs_docx_connus")}
        self.anomalies: list[Anomalie] = []
        self.plafond = corpus.plafonds.anomalies_max

    def signaler(
        self, partie: str, position: int | None, procede: str, texte: str, **detail: Any
    ) -> bool:
        texte = texte.strip()
        if not texte:
            return True
        mesure: dict[str, Any] = {"procede": procede, **detail}
        self.anomalies.append(
            Anomalie(
                code=CODE,
                gravite=self.contexte.corpus.gravite(CODE),
                emplacement=Emplacement(partie=partie, position_flux=position),
                extrait=self.contexte.extrait(texte),
                mesure=mesure,
                explication=self.contexte.corpus.explication(CODE),
            )
        )
        if len(self.anomalies) >= self.plafond:
            self.contexte.tronque = True
            return False
        return True

    def partie(self, nom: str, octets: bytes) -> None:
        try:
            racine = ElementTree.fromstring(octets)
        except ElementTree.ParseError:
            self.contexte.tronque = True
            return
        if nom == "word/comments.xml":
            for commentaire in racine.iter(balise("comment")):
                auteur = _val(commentaire, "author") or ""
                if not self.signaler(
                    nom, None, "commentaire", texte_de(commentaire), auteur=auteur
                ):
                    return
            return
        fond_document = _couleur(_val(racine.find(f".//{balise('background')}"), "color")) or (
            1.0,
            1.0,
            1.0,
        )
        parents = {enfant: parent for parent in racine.iter() for enfant in parent}
        for index, paragraphe in enumerate(racine.iter(balise("p"))):
            if not self.paragraphe(nom, index, paragraphe, parents, fond_document):
                return

    def paragraphe(
        self,
        nom: str,
        index: int,
        paragraphe: Element,
        parents: dict[Element, Element],
        fond_document: Couleur,
    ) -> bool:
        ppr = paragraphe.find(balise("pPr"))
        trame_p = _couleur(_val(ppr.find(balise("shd")), "fill")) if ppr is not None else None
        groupes: list[tuple[str, list[str], dict[str, Any]]] = []

        def ajouter(procede: str, texte: str, detail: dict[str, Any]) -> None:
            if groupes and groupes[-1][0] == procede and groupes[-1][2] == detail:
                groupes[-1][1].append(texte)
            else:
                groupes.append((procede, [texte], detail))

        for element in paragraphe.iter():
            if element.tag == balise("fldSimple"):
                libre = _champ_libre(_val(element, "instr") or "", self.connus, self.mots_min)
                if libre:
                    ajouter("code_champ", libre, {})
                continue
            if element.tag != balise("r"):
                continue
            run = element
            if any(
                p.tag == balise("p") and p is not paragraphe for p in self._ancetres(run, parents)
            ):
                continue  # texte d'un paragraphe imbrique, traite avec lui
            instruction = "".join(t.text or "" for t in run.iter(balise("instrText")))
            if instruction:
                libre = _champ_libre(instruction, self.connus, self.mots_min)
                if libre:
                    ajouter("code_champ", libre, {})
                continue
            supprime = "".join(t.text or "" for t in run.iter(balise("delText")))
            if supprime and any(p.tag == balise("del") for p in self._ancetres(run, parents)):
                ajouter("revision_supprimee", supprime, {})
                continue
            texte = texte_de(run)
            if not texte.strip():
                continue
            rpr = run.find(balise("rPr"))
            if rpr is None:
                continue
            if _actif(rpr.find(balise("vanish"))):
                ajouter("vanish", texte, {})
            elif _actif(rpr.find(balise("webHidden"))):
                ajouter("web_hidden", texte, {})
            else:
                taille = _val(rpr.find(balise("sz")))
                couleur = _couleur(_val(rpr.find(balise("color"))))
                trame_r = _couleur(_val(rpr.find(balise("shd")), "fill"))
                fond = trame_r or trame_p or fond_document
                if taille is not None and taille.isdigit() and int(taille) / 2 < self.taille_min:
                    ajouter("taille", texte, {"taille_police": int(taille) / 2})
                elif couleur is not None and distance(couleur, fond) <= self.seuil_couleur:
                    ajouter(
                        "couleur_fond",
                        texte,
                        {
                            "couleur_texte": _val(rpr.find(balise("color"))),
                            "distance_couleur": round(distance(couleur, fond), 4),
                        },
                    )
        for procede, textes, detail in groupes:
            if not self.signaler(nom, index, procede, "".join(textes), **detail):
                return False
        return True

    @staticmethod
    def _ancetres(element: Element, parents: dict[Element, Element]) -> list[Element]:
        resultat: list[Element] = []
        courant = parents.get(element)
        while courant is not None and len(resultat) < 64:
            resultat.append(courant)
            courant = parents.get(courant)
        return resultat


class DocxTexteMasque:
    nom: str = CODE
    types: tuple[str, ...] = ("application/zip",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        docx = lire_docx(contexte)
        analyse = _Analyse(contexte)
        for nom in docx.noms(_PARTIES_TEXTE):
            octets = docx.partie(nom)
            if octets is not None:
                analyse.partie(nom, octets)
        return analyse.anomalies


inscrire(DocxTexteMasque())
