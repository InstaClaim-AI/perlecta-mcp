"""EML_CONTENU_MASQUE : contenu d'un courriel que le destinataire ne voit pas.

Deux familles. Dans les parties HTML, le texte rendu invisible par une regle
de style ou un attribut : display:none, visibility:hidden, taille nulle,
opacite nulle, couleur du fond, texte de pre-en-tete. Entre les parties
alternatives, la divergence : ce que dit la partie texte brut, que lit un
automate, et que la partie HTML, que lit un humain, ne montre pas.

Le HTML est analyse sans etre execute et sans resoudre aucune ressource.
"""

from __future__ import annotations

import email
import re
import unicodedata
from email import policy
from typing import Any

from perlecta.contrat import Anomalie, Emplacement
from perlecta.detection._html import blocs_masques
from perlecta.detection._texte import texte_html
from perlecta.detection.base import Contexte, inscrire

CODE = "EML_CONTENU_MASQUE"
_MOT = re.compile(r"[^\W_]{4,}", re.UNICODE)
_PARTIES_MAX = 200


def _normaliser(mot: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", mot.casefold()) if not unicodedata.combining(c)
    )


def _mots(texte: str) -> list[str]:
    return [_normaliser(m) for m in _MOT.findall(texte)]


def _contenu(partie: Any) -> str:
    try:
        contenu = partie.get_content()
    except Exception:
        try:
            charge = partie.get_payload(decode=True)
        except Exception:
            return ""
        return charge.decode("utf-8", errors="replace") if isinstance(charge, bytes) else ""
    return contenu if isinstance(contenu, str) else ""


class EmlContenuMasque:
    nom: str = CODE
    types: tuple[str, ...] = ("message/rfc822",)

    def analyser(self, contexte: Contexte) -> list[Anomalie]:
        corpus = contexte.corpus
        try:
            message = email.message_from_bytes(contexte.octets, policy=policy.default)
        except Exception as err:
            from perlecta.detection.base import Indisponible

            raise Indisponible(f"courriel illisible : {type(err).__name__}") from err

        anomalies: list[Anomalie] = []
        bruts: list[str] = []
        htmls: list[str] = []
        numero = 0
        seuil_couleur = corpus.seuil("distance_couleur_fond_max")
        for partie in message.walk():
            if partie.is_multipart():
                continue
            numero += 1
            if numero > _PARTIES_MAX:
                contexte.tronque = True
                break
            genre = partie.get_content_type()
            if genre == "text/plain":
                bruts.append(_contenu(partie))
            elif genre == "text/html":
                html = _contenu(partie)
                htmls.append(html)
                for bloc in blocs_masques(html, seuil_couleur):
                    anomalies.append(
                        self._anomalie(
                            contexte,
                            f"partie {numero} (text/html)",
                            bloc.texte,
                            {"procede": bloc.procede, "balise": bloc.balise},
                        )
                    )
                    if len(anomalies) >= corpus.plafonds.anomalies_max:
                        contexte.tronque = True
                        return anomalies

        if bruts and htmls:
            divergence = self._divergence(contexte, "\n".join(bruts), "\n".join(htmls))
            if divergence is not None:
                anomalies.append(divergence)
        return anomalies

    @staticmethod
    def _anomalie(contexte: Contexte, partie: str, texte: str, mesure: dict[str, Any]) -> Anomalie:
        return Anomalie(
            code=CODE,
            gravite=contexte.corpus.gravite(CODE),
            emplacement=Emplacement(partie=partie),
            extrait=contexte.extrait(texte),
            mesure=mesure,
            explication=contexte.corpus.explication(CODE),
        )

    def _divergence(self, contexte: Contexte, brut: str, html: str) -> Anomalie | None:
        corpus = contexte.corpus
        minimum = int(corpus.seuil("divergence_alternatives_mots_min"))
        seuil = corpus.seuil("divergence_alternatives_min")
        mots_brut = set(_mots(brut))
        if len(mots_brut) < minimum:
            return None
        mots_html = set(_mots(texte_html(html)))
        absents = mots_brut - mots_html
        taux = len(absents) / len(mots_brut)
        if taux < seuil:
            return None
        lignes = []
        for ligne in brut.splitlines():
            mots = _mots(ligne)
            if mots and sum(m in absents for m in mots) * 2 >= len(mots):
                lignes.append(ligne.strip())
        return self._anomalie(
            contexte,
            "parties alternatives",
            "\n".join(lignes) or brut.strip(),
            {
                "procede": "divergence_alternatives",
                "mots_texte_brut": len(mots_brut),
                "mots_absents_du_html": len(absents),
                "taux": round(taux, 3),
                "seuil": seuil,
            },
        )


inscrire(EmlContenuMasque())
