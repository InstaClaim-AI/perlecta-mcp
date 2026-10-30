"""Detecteurs. L'import de ce paquet inscrit les detecteurs disponibles."""

from __future__ import annotations

from perlecta.detection import (  # noqa: F401
    car_invisibles,
    docx_texte_masque,
    eml_contenu_masque,
    homoglyphes,
    meta_instruction,
    pdf_action,
    pdf_calque_masque,
    pdf_couleur_fond,
    pdf_divergence_rendu,
    pdf_hors_page,
    pdf_occultation,
    pdf_rendu_invisible,
    pdf_taille_nulle,
)
from perlecta.detection.base import (
    Contexte,
    Detecteur,
    Indisponible,
    inscrire,
    registre,
)

__all__ = ["Contexte", "Detecteur", "Indisponible", "inscrire", "registre"]
