"""Lecture plafonnee d'un document Word (archive OOXML).

Un .docx est une archive ZIP : elle est lue avec un plafond d'expansion, un
refus des chemins traversants et une profondeur nulle (aucune archive
imbriquee n'est ouverte). Seules les parties utiles sont lues, chacune bornee
par le taux d'expansion du corpus et par le volume total deja lu.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from perlecta.detection.base import Contexte, Indisponible

ESPACE_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_ENTREES_MAX = 10_000
_PARTIES_TEXTE = re.compile(
    r"^word/(document|comments|footnotes|endnotes|header\d*|footer\d*)\.xml$"
)
_PARTIES_PROPRIETES = re.compile(r"^docProps/(core|app|custom)\.xml$")


@dataclass
class Docx:
    parties: dict[str, bytes] = field(default_factory=dict)
    refusees: list[str] = field(default_factory=list)

    def partie(self, nom: str) -> bytes | None:
        return self.parties.get(nom)

    def noms(self, motif: re.Pattern[str]) -> list[str]:
        return sorted(n for n in self.parties if motif.match(n))


def _chemin_traversant(nom: str) -> bool:
    normalise = nom.replace("\\", "/")
    if normalise.startswith("/") or re.match(r"^[A-Za-z]:", normalise):
        return True
    return any(morceau in {"..", ""} for morceau in normalise.split("/")[:-1]) or (
        normalise.split("/")[-1] == ".."
    )


def lire_docx(contexte: Contexte) -> Docx:
    """Les parties utiles de l'archive. Leve Indisponible si ce n'est pas un document Word."""
    cle = "docx"
    if cle in contexte.cache:
        valeur = contexte.cache[cle]
        if isinstance(valeur, Indisponible):
            raise valeur
        docx: Docx = valeur
        return docx
    try:
        docx = _lire(contexte)
    except Indisponible as err:
        contexte.cache[cle] = err
        raise
    contexte.cache[cle] = docx
    return docx


def _lire(contexte: Contexte) -> Docx:
    plafonds = contexte.corpus.plafonds
    try:
        archive = zipfile.ZipFile(io.BytesIO(contexte.octets))
    except (zipfile.BadZipFile, ValueError, OSError) as err:
        raise Indisponible("archive illisible") from err
    with archive:
        try:
            entrees = archive.infolist()
        except Exception as err:
            raise Indisponible("archive illisible") from err
        if len(entrees) > _ENTREES_MAX:
            contexte.tronque = True
            entrees = entrees[:_ENTREES_MAX]
        for info in entrees:
            if _chemin_traversant(info.filename):
                raise Indisponible("archive refusee : chemin traversant")
        noms = {info.filename: info for info in entrees}
        if "word/document.xml" not in noms:
            raise Indisponible("archive sans word/document.xml : pas un document Word")

        docx = Docx()
        budget = plafonds.taille_octets_max * plafonds.expansion_archive_max
        lu = 0
        for nom, info in noms.items():
            if not (_PARTIES_TEXTE.match(nom) or _PARTIES_PROPRIETES.match(nom)):
                continue
            taux = info.file_size / max(info.compress_size, 1)
            if taux > plafonds.expansion_archive_max or info.file_size > budget - lu:
                docx.refusees.append(nom)
                contexte.tronque = True
                continue
            try:
                with archive.open(info) as flux:
                    octets = flux.read(info.file_size + 1)
            except Exception:
                docx.refusees.append(nom)
                contexte.tronque = True
                continue
            if len(octets) > info.file_size:
                # l'en-tete ment sur la taille : on ne lit pas plus loin
                docx.refusees.append(nom)
                contexte.tronque = True
                continue
            lu += len(octets)
            docx.parties[nom] = octets
        if "word/document.xml" not in docx.parties:
            raise Indisponible("plafond d'expansion d'archive atteint sur word/document.xml")
        return docx


def balise(nom: str) -> str:
    return f"{{{ESPACE_W}}}{nom}"


def texte_de(element: object) -> str:
    """Le texte montre d'un element : ses w:t, dans l'ordre."""
    from xml.etree.ElementTree import Element

    if not isinstance(element, Element):
        return ""
    return "".join(t.text or "" for t in element.iter(balise("t")))
