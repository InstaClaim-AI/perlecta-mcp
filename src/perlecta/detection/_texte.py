"""Texte des documents, partie par partie, pour les detecteurs de tous formats.

Une partie est une page de PDF, le corps d'un texte brut, une partie MIME
d'un courriel, un composant d'une archive bureautique. Chaque format inscrit
son extracteur ; le resultat est calcule une fois par analyse et partage.

Pour un PDF, seul le texte decode de facon fiable est retenu : une police a
encodage inconnu produirait des points de code qui ne sont pas dans le
document, et donc des anomalies qui n'y sont pas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser

from perlecta.detection.base import Contexte

_PARTIES_MAX = 200


@dataclass(frozen=True)
class PartieTexte:
    nom: str
    page: int | None
    texte: str


Extracteur = Callable[[Contexte], list[PartieTexte]]
_EXTRACTEURS: dict[str, Extracteur] = {}


def inscrire_extracteur(type_mime: str, extracteur: Extracteur) -> None:
    _EXTRACTEURS[type_mime] = extracteur


def types_textuels() -> tuple[str, ...]:
    return tuple(_EXTRACTEURS)


def parties_texte(contexte: Contexte) -> list[PartieTexte]:
    cle = "texte.parties"
    if cle in contexte.cache:
        parties: list[PartieTexte] = contexte.cache[cle]
        return parties
    extracteur = _EXTRACTEURS.get(contexte.type_detecte)
    parties = extracteur(contexte)[:_PARTIES_MAX] if extracteur else []
    contexte.cache[cle] = parties
    return parties


# --- Texte brut ---------------------------------------------------------------


def decoder_texte(octets: bytes) -> str:
    """Decode un texte brut : UTF-16 avec marque d'ordre, sinon UTF-8, sinon cp1252."""
    if octets.startswith((b"\xff\xfe", b"\xfe\xff")):
        return octets.decode("utf-16", errors="replace")
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError:
        texte = octets.decode("cp1252", errors="replace")
    # la marque d'ordre des octets en tete d'un fichier est une convention, pas
    # un caractere dissimule
    return texte.removeprefix("﻿")


def _texte_brut(contexte: Contexte) -> list[PartieTexte]:
    return [PartieTexte("corps", None, decoder_texte(contexte.octets))]


inscrire_extracteur("text/plain", _texte_brut)


# --- PDF ----------------------------------------------------------------------


def _pdf(contexte: Contexte) -> list[PartieTexte]:
    from perlecta.detection._pdf import analyse_pdf, regrouper, texte_du_groupe

    analyse = analyse_pdf(contexte)
    pages: dict[int, list[str]] = {}
    fiables = [s for s in analyse.segments if s.decodage_fiable and s.texte]
    for groupe in regrouper(fiables):
        pages.setdefault(groupe[0].page, []).append(texte_du_groupe(groupe))
    return [
        PartieTexte(f"page {numero}", numero, "\n".join(lignes))
        for numero, lignes in sorted(pages.items())
    ]


inscrire_extracteur("application/pdf", _pdf)


# --- HTML, sans execution ni resolution d'aucune ressource -------------------------


class _TexteHtml(HTMLParser):
    """Collecte le texte d'un HTML. Rien n'est charge, rien n'est execute."""

    _IGNORES = {"script", "style", "head", "title"}
    _BLOCS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self._ignore = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._IGNORES:
            self._ignore += 1
        elif tag in self._BLOCS:
            self.morceaux.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORES and self._ignore:
            self._ignore -= 1
        elif tag in self._BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignore:
            self.morceaux.append(data)

    def texte(self) -> str:
        return "".join(self.morceaux)


def texte_html(html: str) -> str:
    analyseur = _TexteHtml()
    try:
        analyseur.feed(html)
        analyseur.close()
    except Exception:
        pass
    return analyseur.texte()


# --- Courriel -----------------------------------------------------------------


def _courriel(contexte: Contexte) -> list[PartieTexte]:
    import email
    from email import policy

    try:
        message = email.message_from_bytes(contexte.octets, policy=policy.default)
    except Exception:
        return []
    parties: list[PartieTexte] = []
    sujet = str(message.get("Subject", "") or "")
    if sujet:
        parties.append(PartieTexte("sujet", None, sujet))
    numero = 0
    for partie in message.walk():
        if partie.is_multipart():
            continue
        numero += 1
        if numero > _PARTIES_MAX:
            contexte.tronque = True
            break
        genre = partie.get_content_type()
        if genre not in {"text/plain", "text/html"}:
            continue
        try:
            contenu = partie.get_content()
        except Exception:
            try:
                charge = partie.get_payload(decode=True)
            except Exception:
                continue
            contenu = charge.decode("utf-8", errors="replace") if isinstance(charge, bytes) else ""
        if not isinstance(contenu, str) or not contenu:
            continue
        texte = texte_html(contenu) if genre == "text/html" else contenu
        parties.append(PartieTexte(f"partie {numero} ({genre})", None, texte))
    return parties


inscrire_extracteur("message/rfc822", _courriel)


# --- Document Word -----------------------------------------------------------


def _docx(contexte: Contexte) -> list[PartieTexte]:
    from xml.etree import ElementTree

    from perlecta.detection._docx import _PARTIES_TEXTE, balise, lire_docx, texte_de

    docx = lire_docx(contexte)
    parties: list[PartieTexte] = []
    for nom in docx.noms(_PARTIES_TEXTE):
        octets = docx.partie(nom)
        if octets is None:
            continue
        try:
            racine = ElementTree.fromstring(octets)
        except ElementTree.ParseError:
            contexte.tronque = True
            continue
        if nom == "word/comments.xml":
            lignes = [texte_de(c) for c in racine.iter(balise("comment"))]
        else:
            lignes = [texte_de(p) for p in racine.iter(balise("p"))]
        texte = "\n".join(ligne for ligne in lignes if ligne)
        if texte:
            parties.append(PartieTexte(nom, None, texte))
    return parties


inscrire_extracteur("application/zip", _docx)
