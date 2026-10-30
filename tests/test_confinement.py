"""L'analyse confinee rend le meme resultat que l'analyse directe.

C'est analyser_confine que les integrateurs doivent appeler : elle execute le
parsing dans un sous-processus avec limites de ressources.
"""

from __future__ import annotations

from perlecta import analyser, analyser_confine


def test_meme_resultat_que_l_analyse_directe(dossier_pieces) -> None:
    chemin = dossier_pieces / "devis_garage_piege.pdf"
    direct = analyser(chemin)
    confine = analyser_confine(chemin)

    assert confine.empreinte == direct.empreinte
    assert confine.type_detecte == direct.type_detecte
    assert [a.code for a in confine.anomalies] == [a.code for a in direct.anomalies]
    assert [a.extrait for a in confine.anomalies] == [a.extrait for a in direct.anomalies]
    assert confine.synthese is direct.synthese
    assert confine.version_corpus == direct.version_corpus


def test_piece_ordinaire_confinee(dossier_pieces) -> None:
    rapport = analyser_confine(dossier_pieces / "facture_ordinaire.pdf")
    assert rapport.anomalies == ()
