"""Metadonnees des documents : dictionnaire d'information, XMP, proprietes.

Chaque format inscrit son extracteur. Les valeurs sont des chaines, tronquees,
jamais interpretees. Le XML est lu avec ElementTree, sans resolution d'entite
externe ni de ressource ; sa taille est bornee avant lecture.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from xml.etree import ElementTree

from perlecta.detection.base import Contexte

_VALEUR_MAX = 4000
_XML_MAX = 2_000_000
_CHAMPS_MAX = 500


@dataclass(frozen=True)
class Metadonnee:
    partie: str
    champ: str
    valeur: str


Extracteur = Callable[[Contexte], list[Metadonnee]]
_EXTRACTEURS: dict[str, Extracteur] = {}


def inscrire_extracteur(type_mime: str, extracteur: Extracteur) -> None:
    _EXTRACTEURS[type_mime] = extracteur


def types_avec_metadonnees() -> tuple[str, ...]:
    return tuple(_EXTRACTEURS)


def metadonnees(contexte: Contexte) -> list[Metadonnee]:
    cle = "metadonnees"
    if cle in contexte.cache:
        valeurs: list[Metadonnee] = contexte.cache[cle]
        return valeurs
    extracteur = _EXTRACTEURS.get(contexte.type_detecte)
    valeurs = extracteur(contexte)[:_CHAMPS_MAX] if extracteur else []
    contexte.cache[cle] = valeurs
    return valeurs


def _nettoyer(valeur: str) -> str:
    return re.sub(r"\s+", " ", valeur).strip()[:_VALEUR_MAX]


_CONTENEURS_RDF = {"Alt", "Bag", "Seq", "li", "RDF", "Description", "xmpmeta"}


def champs_xml(partie: str, octets: bytes) -> list[Metadonnee]:
    """Tous les textes et attributs d'un document XML, nommes par leur balise.

    Les elements de conteneur RDF (Alt, Bag, Seq, li) prennent le nom de la
    propriete qui les porte : dc:description/rdf:Alt/rdf:li se lit description.
    """
    if len(octets) > _XML_MAX:
        octets = octets[:_XML_MAX]
    try:
        racine = ElementTree.fromstring(octets)
    except ElementTree.ParseError:
        return []
    resultat: list[Metadonnee] = []

    def parcourir(element: ElementTree.Element, porteur: str, profondeur: int) -> None:
        if len(resultat) >= _CHAMPS_MAX or profondeur > 64:
            return
        nom = element.tag.rsplit("}", 1)[-1]
        if nom in _CONTENEURS_RDF and porteur:
            nom = porteur
        if element.text and _nettoyer(element.text):
            resultat.append(Metadonnee(partie, nom, _nettoyer(element.text)))
        for attribut, valeur in element.attrib.items():
            if _nettoyer(valeur) and not attribut.startswith("{http://www.w3.org/XML/"):
                nom_attribut = attribut.rsplit("}", 1)[-1]
                resultat.append(Metadonnee(partie, f"{nom}@{nom_attribut}", _nettoyer(valeur)))
        for enfant in list(element)[:_CHAMPS_MAX]:
            parcourir(enfant, nom, profondeur + 1)

    parcourir(racine, "", 0)
    return resultat


# --- PDF ----------------------------------------------------------------------


def _pdf(contexte: Contexte) -> list[Metadonnee]:
    import pikepdf

    from perlecta.detection._pdf import document_pdf

    document = document_pdf(contexte)
    resultat: list[Metadonnee] = []
    try:
        for cle, valeur in list(document.docinfo.items())[:_CHAMPS_MAX]:
            if isinstance(valeur, pikepdf.String):
                texte = _nettoyer(str(valeur))
                if texte:
                    resultat.append(Metadonnee("Info", str(cle).lstrip("/"), texte))
    except Exception:
        pass
    try:
        xmp = document.Root.get("/Metadata")
        if isinstance(xmp, pikepdf.Stream):
            resultat.extend(champs_xml("XMP", xmp.read_bytes()[:_XML_MAX]))
    except Exception:
        pass
    return resultat


inscrire_extracteur("application/pdf", _pdf)


# --- Document Word -----------------------------------------------------------


def _docx(contexte: Contexte) -> list[Metadonnee]:
    from perlecta.detection._docx import _PARTIES_PROPRIETES, lire_docx

    docx = lire_docx(contexte)
    resultat: list[Metadonnee] = []
    for nom in docx.noms(_PARTIES_PROPRIETES):
        octets = docx.partie(nom)
        if octets is not None:
            resultat.extend(champs_xml(nom, octets))
    return resultat


inscrire_extracteur("application/zip", _docx)
