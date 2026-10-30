"""PDF_DIVERGENCE_RENDU : la couche texte ne dit pas ce que montre le rendu.

Chaque page est rendue en image, lue par reconnaissance optique, et les mots
de la couche texte visible sont cherches dans ce qui a ete lu. Quand une part
suffisante en est absente, les lignes concernees sont rapportees. La couche
texte comparee exclut ce que les autres detecteurs ont deja retenu : seul ce
qui devrait etre visible est compare au rendu.

Detecteur lourd et optionnel : il depend de l'extra « rendu » (pymupdf,
pytesseract) et du programme tesseract. Si l'un manque, il leve Indisponible
et figure dans detecteurs_ignores avec le motif ; il ne fait jamais echouer
l'analyse. Sous analyser_confine, le sous-processus n'a ni le programme dans
son chemin ni le droit d'ecrire les fichiers temporaires de tesseract : le
detecteur y est donc ignore, et le dit.
"""

from __future__ import annotations

import difflib
import re
import time
import unicodedata
from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._pdf import analyse_pdf, attribuer, regrouper, texte_du_groupe
from perlecta.detection._scan import pages_comparees
from perlecta.detection.base import Contexte, Indisponible, inscrire

CODE = "PDF_DIVERGENCE_RENDU"
_MOT = re.compile(r"[^\W_]{4,}", re.UNICODE)
_OCR_MOTS_MAX = 5000


def _normaliser(mot: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", mot.casefold()) if not unicodedata.combining(c)
    )


def _mots(texte: str) -> list[str]:
    return [_normaliser(m) for m in _MOT.findall(texte)]


def _outils() -> tuple[Any, Any, str]:
    try:
        import pymupdf
    except ImportError as err:
        raise Indisponible("extra rendu absent : pymupdf") from err
    try:
        import pytesseract  # type: ignore[import-untyped]
    except ImportError as err:
        raise Indisponible("extra rendu absent : pytesseract") from err
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception as err:
        raise Indisponible("programme tesseract absent") from err
    return pymupdf, pytesseract, version


def _langues(pytesseract: Any, souhaitees: list[str]) -> str | None:
    try:
        disponibles = set(pytesseract.get_languages())
    except Exception:
        return None
    retenues = [langue for langue in souhaitees if langue in disponibles]
    return "+".join(retenues) if retenues else None


def _motif_echec(err: BaseException) -> str:
    """Dire pourquoi, pas seulement que.

    tesseract passe par des fichiers temporaires. Sous analyser_confine, le
    sous-processus a RLIMIT_FSIZE a zero et ne peut ecrire aucun octet : la
    reconnaissance y est impossible par construction. pytesseract remonte alors
    une erreur interne sans rapport avec la cause, qu'il ne faut pas rapporter
    telle quelle a l'integrateur.
    """
    try:
        import resource

        souple, _dur = resource.getrlimit(resource.RLIMIT_FSIZE)
    except (ImportError, AttributeError, OSError):
        souple = -1
    if souple == 0:
        return (
            "pas le droit d'ecrire : tesseract passe par des fichiers temporaires, "
            "que le confinement interdit. La comparaison au rendu demande une "
            "analyse non confinee, dans un conteneur qui confine autrement."
        )
    return f"echec de la reconnaissance : {type(err).__name__}"


class DivergenceRendu:
    nom: str = CODE
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        pymupdf, pytesseract, version = _outils()
        corpus = contexte.corpus
        reglages = corpus.dico("rendu")
        dpi = int(reglages.get("dpi", 150))
        pages_max = int(reglages.get("pages_max", 10))
        langues = _langues(pytesseract, [str(x) for x in reglages.get("langues", [])])
        seuil = corpus.seuil("divergence_rendu_min")
        mots_min = int(corpus.seuil("divergence_rendu_mots_min"))
        budget_s = corpus.plafonds.duree_ms_max / 1000.0 / 2.0

        analyse = analyse_pdf(contexte)
        try:
            document = pymupdf.open(stream=contexte.octets, filetype="pdf")
        except Exception as err:
            raise Indisponible(f"rendu impossible : {type(err).__name__}") from err

        anomalies: list[Anomalie] = []
        debut = time.monotonic()
        with document:
            nombre = min(len(document), len(analyse.pages))
            if nombre > pages_max:
                contexte.tronque = True
            for numero in range(1, min(nombre, pages_max) + 1):
                if time.monotonic() - debut > budget_s:
                    contexte.tronque = True
                    break
                visibles = [
                    s
                    for s in analyse.segments
                    if s.page == numero
                    and s.decodage_fiable
                    and s.texte.strip()
                    and attribuer(analyse, s, corpus) is None
                ]
                lignes = [texte_du_groupe(g) for g in regrouper(visibles)]
                couche = list(dict.fromkeys(m for ligne in lignes for m in _mots(ligne)))
                if len(couche) < mots_min:
                    continue
                try:
                    page = document[numero - 1]
                    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
                    from PIL import Image

                    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    texte_ocr = pytesseract.image_to_string(image, lang=langues)
                except Exception as err:
                    raise Indisponible(_motif_echec(err)) from err
                mots_ocr = set(_mots(texte_ocr))
                liste_ocr = list(mots_ocr)[:_OCR_MOTS_MAX]
                absents = {
                    m
                    for m in couche
                    if m not in mots_ocr and not difflib.get_close_matches(m, liste_ocr, 1, 0.8)
                }
                taux = len(absents) / len(couche)
                # La page a ete comparee, concluante ou non : la couche
                # invisible qu'elle porte est desormais verifiee, et
                # PDF_RENDU_INVISIBLE n'a plus a la signaler en mineure.
                pages_comparees(contexte).add(numero)
                if taux < seuil:
                    continue
                lignes_absentes = [
                    ligne
                    for ligne in lignes
                    if (mots := _mots(ligne)) and sum(m in absents for m in mots) * 2 >= len(mots)
                ]
                mesure: dict[str, Any] = {
                    "mots_couche_texte": len(couche),
                    "mots_absents_du_rendu": len(absents),
                    "taux": round(taux, 3),
                    "seuil": seuil,
                    "dpi": dpi,
                    "langues": langues or "defaut",
                    "tesseract": version,
                }
                anomalies.append(
                    Anomalie(
                        code=CODE,
                        gravite=corpus.gravite(CODE),
                        emplacement=Emplacement(page=numero),
                        extrait=contexte.extrait("\n".join(lignes_absentes)),
                        mesure=mesure,
                        explication=corpus.explication(CODE),
                    )
                )
                if len(anomalies) >= corpus.plafonds.anomalies_max:
                    contexte.tronque = True
                    break
        return anomalies


inscrire(DivergenceRendu())
