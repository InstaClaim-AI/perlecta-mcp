"""Perlecta — revele le contenu present dans un document mais invisible a l'ecran.

De perlegere : lire jusqu'au bout.

    from perlecta import analyser_confine
    rapport = analyser_confine("devis.pdf")

Le texte rapporte dans une anomalie a ete ecrit par un attaquant : donnee
hostile, a echapper a l'affichage et a ne jamais transmettre a un modele de
langage. Voir README.md.
"""

from __future__ import annotations

from perlecta.confinement import EchecConfinement, analyser_confine, depuis_dict
from perlecta.contrat import (
    Anomalie,
    DetecteurIgnore,
    Emplacement,
    Gravite,
    Rapport,
    Synthese,
)
from perlecta.moteur import VERSION_MOTEUR, analyser

__version__ = VERSION_MOTEUR

__all__ = [
    "Anomalie",
    "DetecteurIgnore",
    "EchecConfinement",
    "Emplacement",
    "Gravite",
    "Rapport",
    "Synthese",
    "VERSION_MOTEUR",
    "__version__",
    "analyser",
    "analyser_confine",
    "depuis_dict",
]
