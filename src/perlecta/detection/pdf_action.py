"""PDF_ACTION : actions automatiques, scripts embarques, fichiers joints.

Pure inspection du graphe d'objets avec pikepdf, a partir du catalogue :
/OpenAction, /AA (actions supplementaires du document, des pages, des
annotations et des champs), actions /JavaScript, /Launch, /URI, /GoToR,
/SubmitForm, /ImportData, fichiers joints (/EmbeddedFile, /FileAttachment).

Rien n'est execute, aucune adresse n'est resolue, aucun lien n'est suivi. Le
type d'action et sa cible sont rapportes en extrait, comme une donnee. Le
declencheur distingue ce qui part tout seul (ouverture du document, action de
page) de ce qui attend un clic : un lien cliquable dans un pied de page est
courant dans un document ordinaire.

Ce seul detecteur emet deux codes, parce que ces deux situations n'ont pas la
meme gravite : PDF_ACTION_AUTOMATIQUE pour ce qui part sans l'accord du lecteur,
PDF_LIEN_CLIQUABLE pour le lien qu'il doit cliquer.
"""

from __future__ import annotations

from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._pdf import document_pdf
from perlecta.detection.base import Contexte, inscrire

CODE_AUTOMATIQUE = "PDF_ACTION_AUTOMATIQUE"
CODE_LIEN = "PDF_LIEN_CLIQUABLE"


def code_pour(nature: str, declencheur: str) -> str:
    """Seul un lien que le lecteur doit cliquer est ordinaire.

    Un /Launch, un /SubmitForm ou un script reste une action majeure meme sous un
    clic : ce qui compte n'est pas le geste, c'est ce que l'action declenche.
    """
    if nature == "uri" and declencheur == "clic":
        return CODE_LIEN
    return CODE_AUTOMATIQUE


TYPES_ACTION = {
    "/JavaScript": "javascript",
    "/Launch": "lancement",
    "/URI": "uri",
    "/GoToR": "document_distant",
    "/GoToE": "document_embarque",
    "/SubmitForm": "envoi_formulaire",
    "/ImportData": "import_donnees",
    "/Rendition": "media",
    "/Movie": "media",
    "/Sound": "media",
}
_CLES_IGNOREES = {
    "/Parent",
    "/P",
    "/Prev",
    "/Last",
    "/Dest",
    "/Contents",
    "/Resources",
    "/Metadata",
}
_DECLENCHEURS = {
    "/OpenAction": "ouverture_document",
    "/AA": "automatique",
    "/JavaScript": "ouverture_document",
    "/EmbeddedFiles": "fichier_joint",
    "/A": "clic",
    "/Next": "enchainement",
}
_OBJETS_MAX = 200_000


def _texte(valeur: Any, limite: int) -> str:
    """Rend une chaine ou un flux PDF en texte, tronque. Jamais d'exception."""
    import pikepdf

    try:
        if isinstance(valeur, pikepdf.Stream):
            octets: bytes = valeur.read_bytes()[:limite]
            return octets.decode("utf-8", errors="replace")
        if isinstance(valeur, pikepdf.String):
            return bytes(valeur)[:limite].decode("utf-8", errors="replace")
        if isinstance(valeur, bytes):
            return valeur[:limite].decode("utf-8", errors="replace")
        if isinstance(valeur, str):
            return valeur[:limite]
        return str(valeur)[:limite]
    except Exception:
        return ""


def _fichier(spec: Any, limite: int) -> str:
    """Nom de fichier d'une specification de fichier, chaine ou dictionnaire."""
    import pikepdf

    try:
        if isinstance(spec, pikepdf.Dictionary):
            for cle in ("/UF", "/F", "/DOS", "/Unix", "/Mac"):
                if cle in spec:
                    return _texte(spec[cle], limite)
            return ""
        return _texte(spec, limite)
    except Exception:
        return ""


def _objgen(obj: Any) -> tuple[int, int] | None:
    try:
        og = obj.objgen
    except Exception:
        return None
    return (int(og[0]), int(og[1])) if og and og[0] else None


class Action:
    nom: str = "PDF_ACTION"
    types: tuple[str, ...] = ("application/pdf",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        import pikepdf

        document = document_pdf(contexte)
        anomalies: list[Anomalie] = []
        limite = contexte.corpus.plafonds.extrait_caracteres_max
        plafond_anomalies = contexte.corpus.plafonds.anomalies_max
        pages: dict[tuple[int, int], int] = {}
        try:
            for numero, page in enumerate(document.pages, start=1):
                og = _objgen(page.obj)
                if og is not None:
                    pages[og] = numero
        except Exception:
            contexte.tronque = True

        vus: set[tuple[int, int]] = set()
        signales: set[Any] = set()
        pile: list[tuple[Any, str, int | None, int]] = [(document.Root, "catalogue", None, 0)]
        visites = 0

        def signaler(
            genre: str, cible: str, declencheur: str, page: int | None, detail: str
        ) -> None:
            cle = (genre, cible, declencheur, page)
            if cle in signales:
                return
            signales.add(cle)
            code = code_pour(genre, declencheur)
            anomalies.append(
                Anomalie(
                    code=code,
                    gravite=contexte.corpus.gravite(code),
                    emplacement=Emplacement(page=page, partie=detail),
                    extrait=contexte.extrait(cible),
                    mesure={"type_action": genre, "declencheur": declencheur},
                    explication=contexte.corpus.explication(code),
                )
            )

        while pile and len(anomalies) < plafond_anomalies:
            obj, declencheur, page, profondeur = pile.pop()
            visites += 1
            if visites > _OBJETS_MAX or profondeur > 64:
                contexte.tronque = True
                break
            og = _objgen(obj)
            if og is not None:
                if og in vus:
                    continue
                vus.add(og)
                page = pages.get(og, page)
            try:
                if isinstance(obj, pikepdf.Array):
                    for element in list(obj)[:10_000]:
                        if isinstance(element, (pikepdf.Dictionary, pikepdf.Array, pikepdf.Stream)):
                            pile.append((element, declencheur, page, profondeur + 1))
                    continue
                if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
                    continue
                self._inspecter(obj, declencheur, page, limite, signaler)
                for cle in list(obj.keys())[:10_000]:
                    if cle in _CLES_IGNOREES:
                        continue
                    valeur = obj[cle]
                    if isinstance(valeur, (pikepdf.Dictionary, pikepdf.Array, pikepdf.Stream)):
                        suivant = _DECLENCHEURS.get(cle, declencheur)
                        if cle == "/AA":
                            suivant = "automatique"
                        pile.append((valeur, suivant, page, profondeur + 1))
            except Exception:
                contexte.tronque = True
                continue
        if len(anomalies) >= plafond_anomalies:
            contexte.tronque = True
        return anomalies

    @staticmethod
    def _inspecter(
        obj: Any, declencheur: str, page: int | None, limite: int, signaler: Any
    ) -> None:
        genre = str(obj.get("/S", "")) if "/S" in obj else ""
        detail = f"page {page}" if page else "catalogue"
        if genre in TYPES_ACTION:
            nature = TYPES_ACTION[genre]
            if genre == "/JavaScript":
                cible = _texte(obj.get("/JS", ""), limite)
            elif genre == "/URI":
                cible = _texte(obj.get("/URI", ""), limite)
            elif genre in {"/Launch", "/GoToR", "/GoToE", "/SubmitForm", "/ImportData"}:
                cible = _fichier(obj.get("/F", ""), limite)
                if genre == "/Launch" and not cible and "/Win" in obj:
                    cible = _fichier(obj["/Win"], limite)
            else:
                cible = ""
            signaler(nature, cible or genre, declencheur, page, detail)
            return
        sous_type = str(obj.get("/Subtype", "")) if "/Subtype" in obj else ""
        if sous_type == "/FileAttachment":
            signaler(
                "fichier_joint", _fichier(obj.get("/FS", ""), limite), "annotation", page, detail
            )
        elif sous_type == "/RichMedia":
            signaler("media", "/RichMedia", "annotation", page, detail)
        genre_objet = str(obj.get("/Type", "")) if "/Type" in obj else ""
        if genre_objet == "/Filespec" and "/EF" in obj:
            signaler("fichier_joint", _fichier(obj, limite), declencheur, page, detail)
        elif "/JS" in obj and genre != "/JavaScript":
            signaler("javascript", _texte(obj["/JS"], limite), declencheur, page, detail)


inscrire(Action())
