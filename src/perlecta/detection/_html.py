"""Analyse d'un HTML sans l'executer et sans resoudre aucune ressource.

Le document est parcouru avec l'analyseur de la bibliotheque standard. Les
feuilles de style internes sont lues pour leurs regles simples (balise, classe,
identifiant), les styles en ligne et les attributs de presentation sont
appliques par-dessus. Aucun script n'est evalue, aucune feuille externe ni
image n'est chargee : une adresse distante reste une chaine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from perlecta.detection._pdf import BLANC, Couleur, distance

_VIDES = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}  # fmt: skip
_REGLE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_SELECTEUR = re.compile(r"^([a-zA-Z][\w-]*)?(?:\.([\w-]+))?(?:#([\w-]+))?$")
_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
_NOMS = {
    "white": (1.0, 1.0, 1.0),
    "black": (0.0, 0.0, 0.0),
    "red": (1.0, 0.0, 0.0),
    "green": (0.0, 0.5, 0.0),
    "blue": (0.0, 0.0, 1.0),
    "yellow": (1.0, 1.0, 0.0),
    "gray": (0.5, 0.5, 0.5),
    "grey": (0.5, 0.5, 0.5),
    "silver": (0.75, 0.75, 0.75),
    "navy": (0.0, 0.0, 0.5),
    "maroon": (0.5, 0.0, 0.0),
    "purple": (0.5, 0.0, 0.5),
    "orange": (1.0, 0.65, 0.0),
}
_TAILLES_NULLES = {"0", "0px", "0pt", "0em", "0rem", "0%"}
_NOEUDS_MAX = 200_000


def couleur_css(valeur: str | None) -> Couleur | None:
    """Couleur d'une valeur CSS, None si elle n'est pas lisible. 'transparent' rend None."""
    if not valeur:
        return None
    valeur = valeur.strip().lower()
    m = _HEX.search(valeur)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    m = _RGB.search(valeur)
    if m:
        return tuple(min(255, int(v)) / 255.0 for v in m.groups())  # type: ignore[return-value]
    for mot in re.findall(r"[a-z]+", valeur):
        if mot in _NOMS:
            return _NOMS[mot]
    return None


def declarations(texte: str) -> dict[str, str]:
    resultat: dict[str, str] = {}
    for morceau in texte.split(";"):
        if ":" not in morceau:
            continue
        cle, valeur = morceau.split(":", 1)
        resultat[cle.strip().lower()] = valeur.replace("!important", "").strip().lower()
    return resultat


@dataclass(frozen=True)
class Regle:
    balise: str | None
    classe: str | None
    identifiant: str | None
    declarations: dict[str, str]


def regles_css(feuille: str) -> list[Regle]:
    regles: list[Regle] = []
    feuille = re.sub(r"/\*.*?\*/", " ", feuille, flags=re.DOTALL)
    for selecteurs, corps in _REGLE.findall(feuille):
        decl = declarations(corps)
        if not decl:
            continue
        for selecteur in selecteurs.split(","):
            m = _SELECTEUR.match(selecteur.strip())
            if not m or not any(m.groups()):
                continue
            balise, classe, identifiant = m.groups()
            regles.append(Regle(balise.lower() if balise else None, classe, identifiant, decl))
        if len(regles) > 5000:
            break
    return regles


@dataclass
class BlocMasque:
    procede: str
    balise: str
    textes: list[str] = field(default_factory=list)

    @property
    def texte(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.textes)).strip()


@dataclass
class _Noeud:
    balise: str
    procede: str | None
    fond: Couleur
    bloc: int | None


class AnalyseurMasquage(HTMLParser):
    """Collecte les textes rendus invisibles par une regle de style ou un attribut."""

    def __init__(self, seuil_couleur: float) -> None:
        super().__init__(convert_charrefs=True)
        self.seuil = seuil_couleur
        self.regles: list[Regle] = []
        self.pile: list[_Noeud] = []
        self.blocs: list[BlocMasque] = []
        self._dans_style = False
        self._noeuds = 0

    # -- style --

    def _style_de(self, balise: str, attributs: dict[str, str | None]) -> dict[str, str]:
        classes = set((attributs.get("class") or "").split())
        identifiant = attributs.get("id")
        decl: dict[str, str] = {}
        for regle in self.regles:
            if regle.balise not in (None, balise):
                continue
            if regle.classe is not None and regle.classe not in classes:
                continue
            if regle.identifiant is not None and regle.identifiant != identifiant:
                continue
            decl.update(regle.declarations)
        decl.update(declarations(attributs.get("style") or ""))
        return decl

    def _procede(
        self, balise: str, attributs: dict[str, str | None], decl: dict[str, str], fond: Couleur
    ) -> str | None:
        if balise in {"script", "style", "head", "title", "template"}:
            return None
        if decl.get("display") == "none":
            return "display_none"
        if decl.get("visibility") == "hidden":
            return "visibility_hidden"
        if "hidden" in attributs:
            return "attribut_hidden"
        if decl.get("opacity") in {"0", "0.0", "0%"}:
            return "opacite_nulle"
        if decl.get("font-size") in _TAILLES_NULLES:
            return "taille_nulle"
        if decl.get("mso-hide") == "all":
            return "mso_hide"
        if decl.get("overflow") == "hidden" and (
            decl.get("max-height") in _TAILLES_NULLES or decl.get("height") in _TAILLES_NULLES
        ):
            return "preentete"
        couleur_texte = decl.get("color") or attributs.get("color")
        if couleur_texte and couleur_texte.strip().lower() == "transparent":
            return "couleur_fond"
        couleur = couleur_css(couleur_texte)
        if couleur is not None and distance(couleur, fond) <= self.seuil:
            return "couleur_fond"
        return None

    # -- parcours --

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._noeuds += 1
        if self._noeuds > _NOEUDS_MAX:
            return
        if tag == "style":
            self._dans_style = True
        attributs = {cle.lower(): valeur for cle, valeur in attrs}
        decl = self._style_de(tag, attributs)
        parent = self.pile[-1] if self.pile else None
        fond = (
            couleur_css(decl.get("background-color"))
            or couleur_css(decl.get("background"))
            or couleur_css(attributs.get("bgcolor"))
            or (parent.fond if parent else BLANC)
        )
        procede = self._procede(tag, attributs, decl, fond)
        herite = parent.procede if parent else None
        bloc = parent.bloc if parent else None
        if procede is not None and herite is None:
            self.blocs.append(BlocMasque(procede, tag))
            bloc = len(self.blocs) - 1
        noeud = _Noeud(tag, procede or herite, fond, bloc)
        if tag not in _VIDES:
            self.pile.append(noeud)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VIDES:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._dans_style = False
        for index in range(len(self.pile) - 1, -1, -1):
            if self.pile[index].balise == tag:
                del self.pile[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._dans_style:
            self.regles.extend(regles_css(data))
            return
        if self.pile and self.pile[-1].bloc is not None and self.pile[-1].procede:
            self.blocs[self.pile[-1].bloc].textes.append(data)


def blocs_masques(html: str, seuil_couleur: float) -> list[BlocMasque]:
    analyseur = AnalyseurMasquage(seuil_couleur)
    try:
        analyseur.feed(html)
        analyseur.close()
    except Exception:
        pass
    return [bloc for bloc in analyseur.blocs if bloc.texte]
