"""Service autonome : une API mince, sans etat.

Envoi d'un document en multipart, reponse le rapport en JSON. Rien n'est
ecrit, rien du contenu n'est journalise : seule l'empreinte figure dans les
journaux techniques. L'analyse passe par analyser_confine, et le plafond de
taille est applique a la lecture du corps, avant toute analyse.

C'est ce qui permet une revue de securite de deux pages : un point d'entree,
aucune persistance, aucune sortie reseau.
"""

from __future__ import annotations

import logging
from typing import Any

from perlecta.confinement import analyser_confine
from perlecta.moteur import VERSION_MOTEUR
from perlecta.reglage import CORPUS_DEFAUT, charger

try:
    from fastapi import FastAPI, HTTPException, UploadFile
    from fastapi.concurrency import run_in_threadpool
except ImportError as err:  # pragma: no cover
    raise ImportError("extra service absent : pip install 'perlecta[service]'") from err

journal = logging.getLogger("perlecta.service")


def creer_application(version_corpus: str = CORPUS_DEFAUT) -> FastAPI:
    corpus = charger(version_corpus)
    taille_max = corpus.plafonds.taille_octets_max
    application = FastAPI(
        title="Perlecta",
        version=VERSION_MOTEUR,
        description="Reveals content that is present in a document but invisible on screen.",
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/version")
    def version() -> dict[str, str]:
        return {"version_moteur": VERSION_MOTEUR, "version_corpus": corpus.version}

    @application.post("/analyses")
    async def analyser_piece(file: UploadFile) -> dict[str, Any]:
        octets = await file.read(taille_max + 1)
        if len(octets) > taille_max:
            raise HTTPException(
                status_code=413, detail="document larger than the size cap of the corpus"
            )
        rapport = await run_in_threadpool(analyser_confine, octets, None, version_corpus)
        journal.info(
            "analysis fingerprint=%s size=%d summary=%s duration_ms=%d truncated=%s",
            rapport.empreinte,
            rapport.taille_octets,
            rapport.synthese.value,
            rapport.duree_ms,
            rapport.tronque,
        )
        return rapport.en_dict()

    return application


def servir(hote: str, port: int, version_corpus: str = CORPUS_DEFAUT) -> int:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run(
        creer_application(version_corpus),
        host=hote,
        port=port,
        access_log=False,
        log_level="info",
    )
    return 0
