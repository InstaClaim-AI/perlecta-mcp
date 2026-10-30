"""Interprete partage des flux de contenu PDF.

Un seul parcours par document, mis en cache dans le contexte, dont tous les
detecteurs PDF lisent le resultat : les segments de texte avec leur etat
graphique effectif, les aplats peints, les boites des pages et les calques
desactives.

L'etat graphique est tenu completement : la matrice courante (cm) et la
matrice de texte (Tm, Td, T*), la couleur de remplissage et son espace, le
mode de rendu, l'opacite, la police et sa taille. Tout cela est empile par q
et restaure par Q, et survit a BT/ET. Les XObjects de forme sont parcourus
avec leur matrice, a profondeur bornee. Rien du document n'est execute.

Les detecteurs se repartissent les segments par ordre de precedence : un
segment signale par un detecteur ne l'est pas par un autre.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._pdf_texte import Police, police_depuis
from perlecta.detection.base import Contexte, Indisponible
from perlecta.reglage import Corpus

Matrice = tuple[float, float, float, float, float, float]
Rect = tuple[float, float, float, float]
Couleur = tuple[float, float, float]

IDENTITE: Matrice = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
BLANC: Couleur = (1.0, 1.0, 1.0)
NOIR: Couleur = (0.0, 0.0, 0.0)
MEDIABOX_DEFAUT: Rect = (0.0, 0.0, 612.0, 792.0)

_PROFONDEUR_PARENTS = 64
_DESCENTE, _MONTEE = 0.22, 0.80
_ESPACE_TJ = -150.0

MODES_INVISIBLES = frozenset({3, 7})
_OPERATEURS_TEXTE = frozenset({"Tj", "TJ", "'", '"'})
_OPERATEURS_REMPLISSAGE = frozenset({"f", "F", "f*", "B", "B*", "b", "b*"})
_OPERATEURS_PEINTURE = _OPERATEURS_REMPLISSAGE | frozenset({"S", "s", "n"})


# --- Geometrie ----------------------------------------------------------------


def multiplier(m: Matrice, n: Matrice) -> Matrice:
    """Produit m x n : m est appliquee d'abord, puis n."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + b * c2,
        a * b2 + b * d2,
        c * a2 + d * c2,
        c * b2 + d * d2,
        e * a2 + f * c2 + e2,
        e * b2 + f * d2 + f2,
    )


def appliquer(m: Matrice, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def echelle(m: Matrice) -> float:
    """Echelle verticale de la matrice : ce qu'un point de police devient."""
    return math.hypot(m[1], m[3])


def boite(points: Iterable[tuple[float, float]]) -> Rect:
    xs, ys = zip(*points, strict=True)
    return (min(xs), min(ys), max(xs), max(ys))


def transformer_rect(m: Matrice, r: Rect) -> Rect:
    x0, y0, x1, y1 = r
    return boite(appliquer(m, x, y) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)))


def contient(exterieur: Rect, interieur: Rect, marge: float = 0.0) -> bool:
    return (
        interieur[0] >= exterieur[0] - marge
        and interieur[1] >= exterieur[1] - marge
        and interieur[2] <= exterieur[2] + marge
        and interieur[3] <= exterieur[3] + marge
    )


def disjoints(a: Rect, b: Rect, marge: float = 0.0) -> bool:
    return a[2] < b[0] - marge or a[0] > b[2] + marge or a[3] < b[1] - marge or a[1] > b[3] + marge


def contient_point(r: Rect, x: float, y: float) -> bool:
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


def union(rects: Iterable[Rect]) -> Rect:
    liste = list(rects)
    return (
        min(r[0] for r in liste),
        min(r[1] for r in liste),
        max(r[2] for r in liste),
        max(r[3] for r in liste),
    )


def _axial(m: Matrice) -> bool:
    return abs(m[1]) < 1e-6 and abs(m[2]) < 1e-6


# --- Couleur ------------------------------------------------------------------


def luminance(c: Couleur) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def distance(a: Couleur, b: Couleur) -> float:
    """Distance euclidienne normalisee entre deux couleurs RVB, entre 0 et 1."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) / 3.0)


def _borner(v: float) -> float:
    return min(1.0, max(0.0, v))


def gris(g: float) -> Couleur:
    return (_borner(g),) * 3


def cmjn(c: float, m: float, j: float, n: float) -> Couleur:
    return (
        _borner((1 - _borner(c)) * (1 - _borner(n))),
        _borner((1 - _borner(m)) * (1 - _borner(n))),
        _borner((1 - _borner(j)) * (1 - _borner(n))),
    )


# --- Resultat du parcours -----------------------------------------------------


@dataclass
class Segment:
    """Un operateur de texte avec l'etat graphique effectif sous lequel il a ete montre."""

    page: int
    position_flux: int
    ordre: int
    texte: str
    decodage: str
    glyphes: int
    taille: float
    mode_rendu: int
    couleur: Couleur | None
    couleur_trait: Couleur | None
    alpha: float
    rect: Rect
    calques_masques: tuple[str, ...]
    police: str
    imbrication: int

    @property
    def vide(self) -> bool:
        """Rien a reveler : du blanc, ou du texte indecodable sans glyphe."""
        return not self.texte.strip() and self.decodage != "inconnu"

    @property
    def invisible_par_rendu(self) -> bool:
        return self.mode_rendu in MODES_INVISIBLES

    @property
    def decodage_fiable(self) -> bool:
        return self.decodage in {"tounicode", "winansi", "macroman"}


@dataclass
class Aplat:
    """Une zone peinte : rectangle rempli ou image, dans l'ordre de trace."""

    page: int
    ordre: int
    rect: Rect
    couleur: Couleur | None
    alpha: float
    image: bool
    rectangulaire: bool
    masque_calque: bool

    @property
    def opaque(self) -> bool:
        return self.alpha >= 0.999 and not self.masque_calque


@dataclass
class PageInfo:
    numero: int
    mediabox: Rect
    cropbox: Rect
    rotation: int


@dataclass
class AnalysePdf:
    pages: list[PageInfo] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    aplats: list[Aplat] = field(default_factory=list)
    calques_desactives: dict[str, str] = field(default_factory=dict)
    tronque: bool = False
    motifs: list[str] = field(default_factory=list)
    _attributions: dict[tuple[int, int], tuple[str, dict[str, Any]] | None] = field(
        default_factory=dict, repr=False
    )
    # Faits de page partages entre detecteurs, calcules a la demande (voir
    # _scan.py). Jamais serialise, jamais rapporte.
    faits_scan: dict[int, Any] = field(default_factory=dict, repr=False)

    def page(self, numero: int) -> PageInfo | None:
        for p in self.pages:
            if p.numero == numero:
                return p
        return None

    def aplats_de(self, page: int) -> list[Aplat]:
        return [a for a in self.aplats if a.page == page]


# --- Etat graphique -----------------------------------------------------------


@dataclass
class _Etat:
    ctm: Matrice = IDENTITE
    couleur: Couleur | None = NOIR
    espace: Any = "gris"
    couleur_trait: Couleur | None = NOIR
    espace_trait: Any = "gris"
    alpha: float = 1.0
    masque_doux: bool = False
    mode_rendu: int = 0
    police: Police | None = None
    taille: float = 0.0
    tc: float = 0.0
    tw: float = 0.0
    th: float = 1.0
    tl: float = 0.0
    ts: float = 0.0


def _nombre(valeur: Any, defaut: float = 0.0) -> float:
    try:
        resultat = float(valeur)
    except (TypeError, ValueError, ArithmeticError):
        return defaut
    if math.isnan(resultat) or math.isinf(resultat):
        return defaut
    return resultat


def _nombres(operandes: list[Any]) -> list[float]:
    return [_nombre(v) for v in operandes]


def _octets(valeur: Any) -> bytes:
    try:
        return bytes(valeur)
    except (TypeError, ValueError):
        return b""


def _nom(valeur: Any) -> str:
    try:
        return str(valeur)
    except Exception:
        return ""


def _objgen(obj: Any) -> tuple[int, int] | None:
    try:
        og = obj.objgen
    except Exception:
        return None
    return (int(og[0]), int(og[1])) if og and og[0] else None


# --- Interprete ---------------------------------------------------------------


class _Interprete:
    def __init__(self, document: Any, corpus: Corpus, pikepdf: Any) -> None:
        self.document = document
        self.corpus = corpus
        self.pikepdf = pikepdf
        self.resultat = AnalysePdf()
        self.operateurs = 0
        self.plafond_operateurs = corpus.plafonds.operateurs_flux_max
        self.profondeur_max = corpus.plafonds.profondeur_imbrication_max
        self.polices: dict[Any, Police] = {}
        self.calques_off: set[tuple[int, int]] = set()
        self.noms_off: set[str] = set()
        self._ordre = 0
        self._lire_calques()

    # -- document --

    def _lire_calques(self) -> None:
        try:
            proprietes = self.document.Root.get("/OCProperties")
            if proprietes is None:
                return
            defaut = proprietes.get("/D")
            if defaut is None:
                return
            for groupe in list(defaut.get("/OFF", []))[:10_000]:
                if not isinstance(groupe, self.pikepdf.Dictionary):
                    continue
                nom = _nom(groupe.get("/Name", ""))
                og = _objgen(groupe)
                if og is not None:
                    self.calques_off.add(og)
                    self.resultat.calques_desactives[f"{og[0]} {og[1]}"] = nom
                elif nom:
                    self.noms_off.add(nom)
                    self.resultat.calques_desactives[nom] = nom
        except Exception:
            self._tronquer("groupes de contenu optionnels illisibles")

    def _tronquer(self, motif: str) -> None:
        self.resultat.tronque = True
        if motif not in self.resultat.motifs:
            self.resultat.motifs.append(motif)

    def parcourir(self) -> AnalysePdf:
        plafond_pages = self.corpus.plafonds.pages_max
        try:
            pages = self.document.pages
            nombre = len(pages)
        except Exception:
            raise Indisponible("arbre des pages illisible") from None
        for numero in range(1, nombre + 1):
            if numero > plafond_pages:
                self._tronquer("plafond de pages atteint")
                break
            if self.operateurs > self.plafond_operateurs:
                self._tronquer("plafond d'operateurs atteint")
                break
            try:
                page = pages[numero - 1]
            except Exception:
                self._tronquer(f"page {numero} illisible")
                continue
            self._page(numero, page)
        return self.resultat

    # -- pages --

    def _herite(self, page_obj: Any, cle: str) -> Any:
        noeud = page_obj
        for _ in range(_PROFONDEUR_PARENTS):
            if noeud is None:
                return None
            try:
                if cle in noeud:
                    return noeud[cle]
                noeud = noeud.get("/Parent")
            except Exception:
                return None
        return None

    def _rect(self, valeur: Any) -> Rect | None:
        try:
            nombres = [_nombre(v) for v in valeur]
        except Exception:
            return None
        if len(nombres) != 4:
            return None
        x0, y0, x1, y1 = nombres
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def _page(self, numero: int, page: Any) -> None:
        obj = page.obj if hasattr(page, "obj") else page
        mediabox = self._rect(self._herite(obj, "/MediaBox")) or MEDIABOX_DEFAUT
        cropbox = self._rect(self._herite(obj, "/CropBox")) or mediabox
        cropbox = (
            max(cropbox[0], mediabox[0]),
            max(cropbox[1], mediabox[1]),
            min(cropbox[2], mediabox[2]),
            min(cropbox[3], mediabox[3]),
        )
        if cropbox[0] >= cropbox[2] or cropbox[1] >= cropbox[3]:
            cropbox = mediabox
        rotation = int(_nombre(self._herite(obj, "/Rotate"), 0.0)) % 360
        self.resultat.pages.append(PageInfo(numero, mediabox, cropbox, rotation))

        ressources = self._herite(obj, "/Resources")
        try:
            instructions = self.pikepdf.parse_content_stream(page)
        except Exception:
            self._tronquer(f"flux de contenu de la page {numero} illisible")
            return
        self._ordre = 0
        self._executer(instructions, ressources, _Etat(), numero, 0, None, (), ())

    # -- ressources --

    def _ressource(self, ressources: Any, categorie: str, nom: str) -> Any:
        try:
            if ressources is None or categorie not in ressources:
                return None
            groupe = ressources[categorie]
            if nom in groupe:
                return groupe[nom]
        except Exception:
            return None
        return None

    def _police(self, ressources: Any, nom: str) -> Police:
        dico = self._ressource(ressources, "/Font", nom)
        if dico is None:
            return Police(nom=nom)
        cle: Any = _objgen(dico) or (id(ressources), nom)
        police = self.polices.get(cle)
        if police is None:
            police = police_depuis(dico, nom)
            self.polices[cle] = police
        return police

    def _espace(self, ressources: Any, nom: str) -> Any:
        if nom in {"/DeviceGray", "/G", "/CalGray"}:
            return "gris"
        if nom in {"/DeviceRGB", "/RGB", "/CalRGB"}:
            return "rgb"
        if nom in {"/DeviceCMYK", "/CMYK"}:
            return "cmyk"
        if nom == "/Pattern":
            return None
        definition = self._ressource(ressources, "/ColorSpace", nom)
        return self._espace_depuis(definition, 0)

    def _espace_depuis(self, definition: Any, profondeur: int) -> Any:
        if definition is None or profondeur > 4:
            return None
        try:
            if isinstance(definition, self.pikepdf.Name):
                return self._espace(None, _nom(definition))
            famille = _nom(definition[0])
            if famille in {"/DeviceGray", "/CalGray", "/G"}:
                return "gris"
            if famille in {"/DeviceRGB", "/CalRGB", "/RGB"}:
                return "rgb"
            if famille in {"/DeviceCMYK", "/CMYK"}:
                return "cmyk"
            if famille == "/ICCBased":
                n = int(_nombre(definition[1].get("/N", 0)))
                return {1: "gris", 3: "rgb", 4: "cmyk"}.get(n)
            if famille == "/Indexed" and len(definition) >= 4:
                base = self._espace_depuis(definition[1], profondeur + 1)
                table = definition[3]
                octets = table.read_bytes() if hasattr(table, "read_bytes") else _octets(table)
                return ("indexe", base, octets)
            if famille == "/Separation" and len(definition) >= 2:
                return ("separation", _nom(definition[1]))
        except Exception:
            return None
        return None

    def _couleur(self, espace: Any, operandes: list[Any]) -> Couleur | None:
        nombres = [_nombre(v) for v in operandes if not isinstance(v, self.pikepdf.Name)]
        if espace == "gris" and len(nombres) >= 1:
            return gris(nombres[0])
        if espace == "rgb" and len(nombres) >= 3:
            return (_borner(nombres[0]), _borner(nombres[1]), _borner(nombres[2]))
        if espace == "cmyk" and len(nombres) >= 4:
            return cmjn(*nombres[:4])
        if isinstance(espace, tuple) and espace and espace[0] == "indexe" and nombres:
            base, table = espace[1], espace[2]
            composantes = {"gris": 1, "rgb": 3, "cmyk": 4}.get(base)
            if composantes is None:
                return None
            index = int(nombres[0])
            morceau = table[index * composantes : (index + 1) * composantes]
            if len(morceau) < composantes:
                return None
            return self._couleur(base, [b / 255.0 for b in morceau])
        if isinstance(espace, tuple) and espace and espace[0] == "separation" and nombres:
            teinte = _borner(nombres[0])
            if espace[1] in {"/Black", "/All"}:
                return gris(1.0 - teinte)
            if espace[1] == "/None":
                return None
            return None
        if espace is None and not isinstance(espace, tuple):
            return None
        return None

    def _calques(self, ressources: Any, proprietes: Any) -> tuple[str, ...]:
        """Noms des calques desactives qui masquent ce contenu, vide s'il est visible."""
        try:
            if isinstance(proprietes, self.pikepdf.Name):
                proprietes = self._ressource(ressources, "/Properties", _nom(proprietes))
            if not isinstance(proprietes, self.pikepdf.Dictionary):
                return ()
            genre = _nom(proprietes.get("/Type", ""))
            if genre == "/OCG":
                return (self._nom_calque(proprietes),) if self._eteint(proprietes) else ()
            if genre == "/OCMD":
                groupes = proprietes.get("/OCGs")
                if isinstance(groupes, self.pikepdf.Dictionary):
                    liste = [groupes]
                elif isinstance(groupes, self.pikepdf.Array):
                    liste = [
                        g for g in list(groupes)[:1000] if isinstance(g, self.pikepdf.Dictionary)
                    ]
                else:
                    return ()
                eteints = [g for g in liste if self._eteint(g)]
                politique = _nom(proprietes.get("/P", "/AnyOn"))
                masque = {
                    "/AnyOn": len(eteints) == len(liste) and bool(liste),
                    "/AllOn": bool(eteints),
                    "/AnyOff": not eteints,
                    "/AllOff": len(eteints) < len(liste),
                }.get(politique, len(eteints) == len(liste) and bool(liste))
                return tuple(self._nom_calque(g) for g in eteints) if masque else ()
        except Exception:
            return ()
        return ()

    def _eteint(self, groupe: Any) -> bool:
        og = _objgen(groupe)
        if og is not None:
            return og in self.calques_off
        try:
            return _nom(groupe.get("/Name", "")) in self.noms_off
        except Exception:
            return False

    def _nom_calque(self, groupe: Any) -> str:
        try:
            nom = _nom(groupe.get("/Name", ""))
        except Exception:
            nom = ""
        og = _objgen(groupe)
        return nom or (f"{og[0]} {og[1]}" if og else "?")

    # -- flux --

    def _executer(
        self,
        instructions: list[Any],
        ressources: Any,
        etat: _Etat,
        numero: int,
        profondeur: int,
        position_base: int | None,
        pile_xobjets: tuple[tuple[int, int], ...],
        calques_herites: tuple[str, ...],
    ) -> None:
        pile: list[_Etat] = []
        tm: Matrice = IDENTITE
        tlm: Matrice = IDENTITE
        marques: list[tuple[str, ...]] = []
        rects: list[Rect] = []
        points: list[tuple[float, float]] = []

        def calques_actifs() -> tuple[str, ...]:
            return calques_herites + tuple(n for groupe in marques for n in groupe)

        for index, instruction in enumerate(instructions):
            self.operateurs += 1
            if self.operateurs > self.plafond_operateurs:
                self._tronquer("plafond d'operateurs atteint")
                return
            position = position_base if position_base is not None else index
            try:
                operateur = str(instruction.operator)
                operandes = list(instruction.operands)
            except Exception:
                continue
            try:
                if operateur == "q":
                    if len(pile) < 256:
                        pile.append(replace(etat))
                elif operateur == "Q":
                    if pile:
                        etat = pile.pop()
                elif operateur == "cm" and len(operandes) >= 6:
                    n = _nombres(operandes[:6])
                    etat.ctm = multiplier((n[0], n[1], n[2], n[3], n[4], n[5]), etat.ctm)
                elif operateur == "gs" and operandes:
                    self._etat_etendu(etat, ressources, _nom(operandes[0]))

                # couleur de remplissage
                elif operateur == "g" and operandes:
                    etat.espace, etat.couleur = "gris", gris(_nombre(operandes[0]))
                elif operateur == "rg" and len(operandes) >= 3:
                    etat.espace, etat.couleur = "rgb", self._couleur("rgb", operandes)
                elif operateur == "k" and len(operandes) >= 4:
                    etat.espace, etat.couleur = "cmyk", self._couleur("cmyk", operandes)
                elif operateur == "cs" and operandes:
                    etat.espace = self._espace(ressources, _nom(operandes[0]))
                    etat.couleur = NOIR if etat.espace in {"gris", "rgb", "cmyk"} else None
                elif operateur in {"sc", "scn"}:
                    etat.couleur = self._couleur(etat.espace, operandes)
                # couleur de trait
                elif operateur == "G" and operandes:
                    etat.espace_trait, etat.couleur_trait = "gris", gris(_nombre(operandes[0]))
                elif operateur == "RG" and len(operandes) >= 3:
                    etat.espace_trait = "rgb"
                    etat.couleur_trait = self._couleur("rgb", operandes)
                elif operateur == "K" and len(operandes) >= 4:
                    etat.espace_trait = "cmyk"
                    etat.couleur_trait = self._couleur("cmyk", operandes)
                elif operateur == "CS" and operandes:
                    etat.espace_trait = self._espace(ressources, _nom(operandes[0]))
                    etat.couleur_trait = (
                        NOIR if etat.espace_trait in {"gris", "rgb", "cmyk"} else None
                    )
                elif operateur in {"SC", "SCN"}:
                    etat.couleur_trait = self._couleur(etat.espace_trait, operandes)

                # texte
                elif operateur == "BT":
                    tm = tlm = IDENTITE
                elif operateur == "Tc" and operandes:
                    etat.tc = _nombre(operandes[0])
                elif operateur == "Tw" and operandes:
                    etat.tw = _nombre(operandes[0])
                elif operateur == "Tz" and operandes:
                    etat.th = _nombre(operandes[0], 100.0) / 100.0
                elif operateur == "TL" and operandes:
                    etat.tl = _nombre(operandes[0])
                elif operateur == "Ts" and operandes:
                    etat.ts = _nombre(operandes[0])
                elif operateur == "Tr" and operandes:
                    etat.mode_rendu = int(_nombre(operandes[0], etat.mode_rendu))
                elif operateur == "Tf" and len(operandes) >= 2:
                    etat.police = self._police(ressources, _nom(operandes[0]))
                    etat.taille = _nombre(operandes[1])
                elif operateur == "Td" and len(operandes) >= 2:
                    n = _nombres(operandes[:2])
                    tlm = multiplier((1.0, 0.0, 0.0, 1.0, n[0], n[1]), tlm)
                    tm = tlm
                elif operateur == "TD" and len(operandes) >= 2:
                    n = _nombres(operandes[:2])
                    etat.tl = -n[1]
                    tlm = multiplier((1.0, 0.0, 0.0, 1.0, n[0], n[1]), tlm)
                    tm = tlm
                elif operateur == "Tm" and len(operandes) >= 6:
                    n = _nombres(operandes[:6])
                    tlm = tm = (n[0], n[1], n[2], n[3], n[4], n[5])
                elif operateur == "T*":
                    tlm = multiplier((1.0, 0.0, 0.0, 1.0, 0.0, -etat.tl), tlm)
                    tm = tlm
                elif operateur in _OPERATEURS_TEXTE:
                    morceaux: list[Any] = []
                    if operateur == "Tj" and operandes:
                        morceaux = [_octets(operandes[0])]
                    elif operateur == "'" and operandes:
                        tlm = multiplier((1.0, 0.0, 0.0, 1.0, 0.0, -etat.tl), tlm)
                        tm = tlm
                        morceaux = [_octets(operandes[0])]
                    elif operateur == '"' and len(operandes) >= 3:
                        etat.tw, etat.tc = _nombre(operandes[0]), _nombre(operandes[1])
                        tlm = multiplier((1.0, 0.0, 0.0, 1.0, 0.0, -etat.tl), tlm)
                        tm = tlm
                        morceaux = [_octets(operandes[2])]
                    elif operateur == "TJ" and operandes:
                        for element in list(operandes[0])[:10_000]:
                            if isinstance(element, (int, float)) or type(element).__name__ in {
                                "Decimal"
                            }:
                                morceaux.append(_nombre(element))
                            else:
                                octets = _octets(element)
                                if octets:
                                    morceaux.append(octets)
                    tm = self._montrer(
                        morceaux, etat, tm, numero, position, profondeur, calques_actifs()
                    )

                # chemins
                elif operateur == "re" and len(operandes) >= 4:
                    x, y, w, h = _nombres(operandes[:4])
                    rect = (min(x, x + w), min(y, y + h), max(x, x + w), max(y, y + h))
                    rects.append(rect)
                    points.extend([(rect[0], rect[1]), (rect[2], rect[3])])
                elif operateur in {"m", "l"} and len(operandes) >= 2:
                    n = _nombres(operandes[:2])
                    points.append((n[0], n[1]))
                elif operateur == "c" and len(operandes) >= 6:
                    n = _nombres(operandes[:6])
                    points.extend([(n[0], n[1]), (n[2], n[3]), (n[4], n[5])])
                elif operateur in {"v", "y"} and len(operandes) >= 4:
                    n = _nombres(operandes[:4])
                    points.extend([(n[0], n[1]), (n[2], n[3])])
                elif operateur in _OPERATEURS_PEINTURE:
                    if operateur in _OPERATEURS_REMPLISSAGE:
                        self._peindre(rects, points, etat, numero, calques_actifs())
                    rects, points = [], []

                # objets externes et images
                elif operateur == "Do" and operandes:
                    self._xobjet(
                        ressources,
                        _nom(operandes[0]),
                        etat,
                        numero,
                        profondeur,
                        position,
                        pile_xobjets,
                        calques_actifs(),
                    )
                elif operateur in {"INLINE IMAGE", "EI", "BI", "ID"}:
                    if operateur in {"INLINE IMAGE", "EI"}:
                        self._image(etat, numero, calques_actifs())

                # contenu marque
                elif operateur == "BDC":
                    if len(marques) < 256:
                        if len(operandes) >= 2 and _nom(operandes[0]) == "/OC":
                            marques.append(self._calques(ressources, operandes[1]))
                        else:
                            marques.append(())
                elif operateur == "BMC":
                    if len(marques) < 256:
                        marques.append(())
                elif operateur == "EMC" and marques:
                    marques.pop()
            except Exception:
                # un operande malforme n'interrompt pas la page : on poursuit
                continue

    def _etat_etendu(self, etat: _Etat, ressources: Any, nom: str) -> None:
        gs = self._ressource(ressources, "/ExtGState", nom)
        if gs is None:
            return
        try:
            if "/ca" in gs:
                etat.alpha = _borner(_nombre(gs["/ca"], 1.0))
            if "/SMask" in gs:
                etat.masque_doux = _nom(gs["/SMask"]) != "/None"
            if "/Font" in gs and len(gs["/Font"]) >= 2:
                etat.police = police_depuis(gs["/Font"][0], "gs")
                etat.taille = _nombre(gs["/Font"][1])
        except Exception:
            return

    def _montrer(
        self,
        morceaux: list[Any],
        etat: _Etat,
        tm: Matrice,
        numero: int,
        position: int,
        profondeur: int,
        calques: tuple[str, ...],
    ) -> Matrice:
        police = etat.police or Police(nom="")
        taille = etat.taille
        textes: list[str] = []
        decodages: set[str] = set()
        glyphes = 0
        avance = 0.0
        mono_octet = police.octets_par_code == (1,)
        for morceau in morceaux:
            if isinstance(morceau, float):
                avance += -morceau / 1000.0 * taille * etat.th
                if morceau < _ESPACE_TJ and textes and not textes[-1].endswith(" "):
                    textes.append(" ")
                continue
            texte, decodage, codes = police.decoder(morceau)
            textes.append(texte)
            decodages.add(decodage)
            glyphes += len(codes)
            for code in codes:
                mot = etat.tw if (mono_octet and code == 32) else 0.0
                avance += (police.largeur(code) * taille + etat.tc + mot) * etat.th
        if glyphes == 0:
            return tm

        m0 = multiplier(tm, etat.ctm)
        bas, haut = etat.ts - _DESCENTE * taille, etat.ts + _MONTEE * taille
        rect = transformer_rect(m0, (0.0, bas, avance, haut))
        if "inconnu" in decodages:
            fiabilite = "inconnu"
        elif decodages <= {"tounicode"}:
            fiabilite = "tounicode"
        elif decodages <= {"winansi"}:
            fiabilite = "winansi"
        elif decodages <= {"macroman"}:
            fiabilite = "macroman"
        else:
            fiabilite = "approx"
        couleur = etat.couleur_trait if etat.mode_rendu in {1, 5} else etat.couleur
        self._ordre += 1
        self.resultat.segments.append(
            Segment(
                page=numero,
                position_flux=position,
                ordre=self._ordre,
                texte="".join(textes),
                decodage=fiabilite,
                glyphes=glyphes,
                taille=taille * echelle(m0),
                mode_rendu=etat.mode_rendu,
                couleur=couleur,
                couleur_trait=etat.couleur_trait,
                alpha=etat.alpha,
                rect=rect,
                calques_masques=calques,
                police=police.nom,
                imbrication=profondeur,
            )
        )
        return multiplier((1.0, 0.0, 0.0, 1.0, avance, 0.0), tm)

    def _peindre(
        self,
        rects: list[Rect],
        points: list[tuple[float, float]],
        etat: _Etat,
        numero: int,
        calques: tuple[str, ...],
    ) -> None:
        axial = _axial(etat.ctm)
        if rects:
            for rect in rects[:1000]:
                self._ordre += 1
                self.resultat.aplats.append(
                    Aplat(
                        page=numero,
                        ordre=self._ordre,
                        rect=transformer_rect(etat.ctm, rect),
                        couleur=etat.couleur,
                        alpha=0.0 if etat.masque_doux else etat.alpha,
                        image=False,
                        rectangulaire=axial,
                        masque_calque=bool(calques),
                    )
                )
        elif points:
            self._ordre += 1
            self.resultat.aplats.append(
                Aplat(
                    page=numero,
                    ordre=self._ordre,
                    rect=transformer_rect(etat.ctm, boite(points)),
                    couleur=etat.couleur,
                    alpha=0.0 if etat.masque_doux else etat.alpha,
                    image=False,
                    rectangulaire=False,
                    masque_calque=bool(calques),
                )
            )

    def _image(self, etat: _Etat, numero: int, calques: tuple[str, ...]) -> None:
        self._ordre += 1
        self.resultat.aplats.append(
            Aplat(
                page=numero,
                ordre=self._ordre,
                rect=transformer_rect(etat.ctm, (0.0, 0.0, 1.0, 1.0)),
                couleur=None,
                alpha=0.0 if etat.masque_doux else etat.alpha,
                image=True,
                rectangulaire=_axial(etat.ctm),
                masque_calque=bool(calques),
            )
        )

    def _xobjet(
        self,
        ressources: Any,
        nom: str,
        etat: _Etat,
        numero: int,
        profondeur: int,
        position: int,
        pile_xobjets: tuple[tuple[int, int], ...],
        calques: tuple[str, ...],
    ) -> None:
        xobj = self._ressource(ressources, "/XObject", nom)
        if xobj is None:
            return
        try:
            sous_type = _nom(xobj.get("/Subtype", ""))
            calques_xobj = self._calques(ressources, xobj.get("/OC")) if "/OC" in xobj else ()
        except Exception:
            return
        calques_total = calques + calques_xobj
        if sous_type == "/Image":
            self._image(etat, numero, calques_total)
            return
        if sous_type != "/Form":
            return
        if profondeur + 1 > self.profondeur_max:
            self._tronquer("profondeur d'imbrication des XObjects atteinte")
            return
        og = _objgen(xobj)
        if og is not None and og in pile_xobjets:
            self._tronquer("boucle de XObjects")
            return
        etat_fils = replace(etat)
        try:
            if "/Matrix" in xobj:
                n = _nombres(list(xobj["/Matrix"])[:6])
                if len(n) == 6:
                    etat_fils.ctm = multiplier((n[0], n[1], n[2], n[3], n[4], n[5]), etat.ctm)
            ressources_fils = xobj.get("/Resources") or ressources
            instructions = self.pikepdf.parse_content_stream(xobj)
        except Exception:
            self._tronquer(f"XObject {nom} illisible")
            return
        self._executer(
            instructions,
            ressources_fils,
            etat_fils,
            numero,
            profondeur + 1,
            position,
            pile_xobjets + ((og,) if og is not None else ()),
            calques_total,
        )


# --- Acces par les detecteurs ----------------------------------------------------


def document_pdf(contexte: Contexte) -> Any:
    """Le document ouvert par pikepdf, partage entre detecteurs. Leve Indisponible."""
    cle = "pdf.document"
    if cle in contexte.cache:
        valeur = contexte.cache[cle]
        if isinstance(valeur, Indisponible):
            raise valeur
        return valeur
    try:
        import pikepdf
    except ImportError as err:  # pragma: no cover
        erreur = Indisponible("pikepdf absent")
        contexte.cache[cle] = erreur
        raise erreur from err
    try:
        document = pikepdf.open(io.BytesIO(contexte.octets))
    except Exception as err:
        erreur = Indisponible(f"document illisible : {type(err).__name__}")
        contexte.cache[cle] = erreur
        raise erreur from err
    contexte.cache[cle] = document
    return document


def analyse_pdf(contexte: Contexte) -> AnalysePdf:
    """Le parcours des flux de contenu, calcule une fois par analyse."""
    cle = "pdf.analyse"
    if cle in contexte.cache:
        valeur = contexte.cache[cle]
        if isinstance(valeur, Indisponible):
            raise valeur
        resultat: AnalysePdf = valeur
        return resultat
    document = document_pdf(contexte)
    import pikepdf

    try:
        resultat = _Interprete(document, contexte.corpus, pikepdf).parcourir()
    except Indisponible as err:
        contexte.cache[cle] = err
        raise
    except Exception as err:
        erreur = Indisponible(f"flux de contenu illisibles : {type(err).__name__}")
        contexte.cache[cle] = erreur
        raise erreur from err
    if resultat.tronque:
        contexte.tronque = True
    contexte.cache[cle] = resultat
    return resultat


# --- Precedence entre detecteurs ------------------------------------------------

Predicat = Callable[[AnalysePdf, Segment, Corpus], "dict[str, Any] | None"]

PRECEDENCE: tuple[str, ...] = (
    "PDF_RENDU_INVISIBLE",
    "PDF_CALQUE_MASQUE",
    "PDF_HORS_PAGE",
    "PDF_TAILLE_NULLE",
    "PDF_COULEUR_FOND",
    "PDF_OCCULTATION",
)
_PREDICATS: dict[str, Predicat] = {}


def inscrire_predicat(code: str, predicat: Predicat) -> None:
    _PREDICATS[code] = predicat


def attribuer(
    analyse: AnalysePdf, segment: Segment, corpus: Corpus
) -> tuple[str, dict[str, Any]] | None:
    """Le premier code, par precedence, dont le predicat retient le segment.

    C'est ce qui garantit qu'un segment n'est signale que par un detecteur.
    """
    cle = (segment.page, segment.ordre)
    if cle in analyse._attributions:
        return analyse._attributions[cle]
    resultat: tuple[str, dict[str, Any]] | None = None
    for code in PRECEDENCE:
        predicat = _PREDICATS.get(code)
        if predicat is None:
            continue
        mesure = predicat(analyse, segment, corpus)
        if mesure is not None:
            resultat = (code, mesure)
            break
    analyse._attributions[cle] = resultat
    return resultat


def segments_attribues(contexte: Contexte, code: str) -> list[tuple[Segment, dict[str, Any]]]:
    analyse = analyse_pdf(contexte)
    retenus: list[tuple[Segment, dict[str, Any]]] = []
    for segment in analyse.segments:
        attribution = attribuer(analyse, segment, contexte.corpus)
        if attribution is not None and attribution[0] == code:
            retenus.append((segment, attribution[1]))
    return retenus


# --- Regroupement en lignes -----------------------------------------------------


def _meme_ligne(a: Segment, b: Segment) -> bool:
    if a.page != b.page:
        return False
    taille = max(a.taille, b.taille, 1.0)
    if abs(a.rect[1] - b.rect[1]) > 0.5 * taille:
        return False
    ecart = b.rect[0] - a.rect[2]
    return -0.5 * taille <= ecart <= 3.0 * taille


def regrouper(segments: list[Segment]) -> list[list[Segment]]:
    """Regroupe les segments consecutifs d'une meme ligne."""
    groupes: list[list[Segment]] = []
    for segment in segments:
        if groupes and _meme_ligne(groupes[-1][-1], segment):
            groupes[-1].append(segment)
        else:
            groupes.append([segment])
    return groupes


def texte_du_groupe(groupe: list[Segment]) -> str:
    morceaux: list[str] = []
    for precedent, segment in zip([None, *groupe[:-1]], groupe, strict=True):
        if precedent is not None and morceaux:
            ecart = segment.rect[0] - precedent.rect[2]
            if ecart > 0.15 * max(segment.taille, 1.0) and not morceaux[-1].endswith(" "):
                morceaux.append(" ")
        morceaux.append(segment.texte)
    return "".join(morceaux)


def anomalies_par_ligne(
    contexte: Contexte,
    code: str,
    retenus: list[tuple[Segment, dict[str, Any]]],
) -> list[Anomalie]:
    """Une anomalie par ligne de segments retenus, dans l'ordre du document."""
    anomalies: list[Anomalie] = []
    plafond = contexte.corpus.plafonds.anomalies_max
    mesures = {(s.page, s.ordre): m for s, m in retenus}
    for groupe in regrouper([s for s, _ in retenus]):
        premier = groupe[0]
        texte = texte_du_groupe(groupe).strip()
        mesure = dict(mesures[(premier.page, premier.ordre)])
        mesure.setdefault("glyphes", sum(s.glyphes for s in groupe))
        mesure.setdefault("decodage", premier.decodage)
        if len(groupe) > 1:
            mesure["segments"] = len(groupe)
        anomalies.append(
            Anomalie(
                code=code,
                gravite=contexte.corpus.gravite(code),
                emplacement=Emplacement(
                    page=premier.page,
                    rectangle=_arrondir(union(s.rect for s in groupe)),
                    position_flux=premier.position_flux,
                ),
                extrait=contexte.extrait(texte),
                mesure=mesure,
                explication=contexte.corpus.explication(code),
            )
        )
        if len(anomalies) >= plafond:
            contexte.tronque = True
            break
    return anomalies


def _arrondir(r: Rect) -> Rect:
    return (round(r[0], 2), round(r[1], 2), round(r[2], 2), round(r[3], 2))


def arrondir_couleur(c: Couleur | None) -> list[float] | None:
    return None if c is None else [round(v, 3) for v in c]
