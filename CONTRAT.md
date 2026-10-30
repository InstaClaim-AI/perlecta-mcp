# Contrat de Perlecta

Ce document suffit à intégrer Perlecta sans lire son code. Toute évolution incompatible de ce contrat est une évolution majeure de version.

## Appel

```python
from perlecta import analyser_confine, analyser, Rapport

rapport = analyser_confine(source, type_mime=None, version_corpus="v1")  # -> Rapport
rapport = analyser(source, type_mime=None, version_corpus="v1")  # -> Rapport
```

`source` accepte un chemin, des octets ou un flux binaire. `type_mime` force le type ; par défaut il est détecté par signature, jamais par extension.

**Appelez `analyser_confine`.** Elle exécute l'analyse dans un sous-processus avec limites de mémoire, de temps processeur, de descripteurs et d'écriture, sans environnement hérité. `analyser` n'est exposée que pour les appelants qui confinent déjà eux-mêmes.

Le confinement par limites de ressources ne remplace pas le confinement par conteneur : plafonner le nombre de processus relève de l'hôte, pas de ces limites. Sur macOS, l'hôte refuse toute limite de mémoire finie ; elle n'y est pas appliquée et le sous-processus le signale sur sa sortie d'erreur. Le conteneur reste le confinement de référence.

## Rapport

| Champ | Type | Contenu |
|---|---|---|
| `empreinte` | `str` | SHA-256 des octets tels que reçus, avant toute transformation |
| `taille_octets` | `int` | taille analysée |
| `type_detecte` | `str` | type détecté par signature |
| `anomalies` | `tuple[Anomalie, ...]` | ordonnées par gravité décroissante, puis page, puis position |
| `synthese` | `Synthese` | `aucune_anomalie_detectee`, `anomalies_mineures`, `anomalies_majeures` |
| `version_moteur` | `str` | version de Perlecta |
| `version_corpus` | `str` | version du corpus de motifs appliqué |
| `detecteurs_executes` | `tuple[str, ...]` | ceux qui ont effectivement tourné |
| `detecteurs_ignores` | `tuple[DetecteurIgnore, ...]` | ceux qui n'ont pas tourné, avec leur motif |
| `duree_ms` | `int` | durée de l'analyse |
| `tronque` | `bool` | vrai si un plafond a interrompu l'analyse |

`rapport.en_dict()` rend la forme JSON. `perlecta.depuis_dict()` la relit.

**`synthese` n'est pas un verdict de salubrité.** `aucune_anomalie_detectee` signifie que les détecteurs exécutés n'ont rien trouvé. La portée réelle de l'analyse se lit dans `detecteurs_executes`, `detecteurs_ignores` et `tronque`. Un intégrateur qui affiche la synthèse sans ces trois champs présente une analyse partielle comme complète.

Les motifs d'ignorance commencent par une forme stable : `type non pris en charge : …`, `extra rendu absent : …`, `programme tesseract absent`, `plafond de duree atteint`, `document illisible : …`, `archive refusee : …`, `echec : …`.

## Anomalie

| Champ | Type | Contenu |
|---|---|---|
| `code` | `str` | identifiant stable, voir la table des codes |
| `gravite` | `Gravite` | `mineure`, `majeure` |
| `emplacement` | `Emplacement` | `page`, `partie`, `rectangle`, `position_flux` — nuls quand sans objet |
| `extrait` | `str` | **le texte révélé. Donnée hostile.** Tronqué au plafond du corpus |
| `mesure` | `dict` | la preuve numérique, propre à chaque code, voir ci-dessous |
| `explication` | `str` | une phrase factuelle issue du corpus |

`emplacement.rectangle` est exprimé dans l'espace utilisateur de la page, en points, sous la forme `(x0, y0, x1, y1)`. `emplacement.partie` nomme la page, la partie MIME, le composant d'archive ou la source de métadonnée. `position_flux` est l'index de l'opérateur dans le flux de contenu de la page, ou celui du paragraphe dans un document Word.

### L'extrait est une donnée hostile

Ce texte a été écrit par un attaquant pour agir sur un lecteur automatique. C'est l'objet du produit.

- Échappez-le à l'affichage. Ne l'interprétez jamais comme du balisage.
- Ne le transmettez jamais à un modèle de langage, à aucun titre.
- Ne l'insérez jamais dans un gabarit sans échappement.
- Ne le journalisez pas dans un système qui le réinjecterait dans un traitement automatique.

Pour `CAR_INVISIBLES`, les caractères invisibles sont rendus visibles dans l'extrait par leur notation `[U+200B]` ; les points de code exacts sont dans la mesure.

## Codes d'anomalie

| Code | Gravité | Types | État en 0.2.0 | Clés de `mesure` |
|---|---|---|---|---|
| `PDF_RENDU_INVISIBLE` | majeure | PDF | implémenté, hors couche de reconnaissance optique | `mode_rendu`, `x`, `y`, `glyphes`, `decodage` |
| `PDF_COUCHE_NUMERISEE` | mineure | PDF | implémenté, une par page | `mode_rendu`, `segments`, `verifiee_par_le_rendu` |
| `PDF_COULEUR_FOND` | majeure | PDF | implémenté | `couleur_texte`, `couleur_fond`, `distance_couleur`, `luminance_texte`, `luminance_fond`, `seuil` ; ou `procede: opacite_nulle` |
| `PDF_TAILLE_NULLE` | majeure | PDF | implémenté | `taille_police`, `seuil` |
| `PDF_HORS_PAGE` | majeure | PDF | implémenté | `zone_affichee`, `boite` (`CropBox` ou `MediaBox`), `rotation`, `marge` |
| `PDF_CALQUE_MASQUE` | majeure | PDF | implémenté | `calques` |
| `PDF_OCCULTATION` | majeure | PDF | implémenté | `couvert_par` (`rectangle` ou `image`), `rectangle_aplat`, `ordre_texte`, `ordre_aplat` ; `couleur_aplat` pour un rectangle seulement |
| `PDF_ACTION_AUTOMATIQUE` | majeure | PDF | implémenté | `type_action`, `declencheur` |
| `PDF_LIEN_CLIQUABLE` | mineure | PDF | implémenté | `type_action`, `declencheur` |
| `PDF_DIVERGENCE_RENDU` | majeure | PDF | implémenté, optionnel, extra `rendu` | `mots_couche_texte`, `mots_absents_du_rendu`, `taux`, `seuil`, `dpi`, `langues`, `tesseract` |
| `CAR_INVISIBLES` | mineure | PDF, texte, courriel, Word | implémenté | `total`, `par_classe`, `points_de_code` |
| `META_INSTRUCTION` | mineure | PDF, Word | implémenté | `champ`, `motifs` |
| `HOMOGLYPHES` | mineure | PDF, texte, courriel, Word | implémenté | `mots`, `exemples` |
| `DOCX_TEXTE_MASQUE` | majeure | Word | implémenté | `procede` (`vanish`, `web_hidden`, `couleur_fond`, `taille`, `revision_supprimee`, `code_champ`, `commentaire`) et son détail |
| `EML_CONTENU_MASQUE` | majeure | courriel | implémenté | `procede` (`display_none`, `visibility_hidden`, `attribut_hidden`, `opacite_nulle`, `taille_nulle`, `mso_hide`, `preentete`, `couleur_fond`, `divergence_alternatives`) et son détail |

Types détectés par signature : `application/pdf`, `text/plain`, `message/rfc822`, `application/zip` (un document Word est une archive ; une archive sans `word/document.xml` est écartée avec ce motif).

Les détecteurs PDF se répartissent les segments par ordre de précédence — rendu invisible, calque, hors page, taille, couleur, occultation — et un même segment n'est signalé que par un seul d'entre eux. `PDF_DIVERGENCE_RENDU` ne compare au rendu que le texte qu'aucun autre détecteur n'a retenu.

Les actions sont réparties sur deux codes parce qu'elles n'ont pas la même gravité. `PDF_LIEN_CLIQUABLE` ne vise qu'un cas, étroit : un `/URI` que le lecteur doit cliquer. Tout le reste est `PDF_ACTION_AUTOMATIQUE` — y compris un `/Launch` ou un `/SubmitForm` sous un clic, car ce qui compte n'est pas le geste mais ce que l'action déclenche. La cible d'un lien cliquable reste rapportée, à titre d'inventaire des sorties possibles, sans rendre la pièce majeure.

Un code présent au corpus et sans détecteur ne produit jamais de faux négatif silencieux : le détecteur absent n'apparaît pas dans `detecteurs_executes`.

## Plafonds du corpus v1

Taille 50 Mio · pages 500 · durée 20 s · mémoire 1 Gio · expansion d'archive 100 · imbrication 4 · extrait 600 caractères · anomalies 200 · opérateurs de flux 2 000 000.

Un plafond atteint **tronque et rapporte**. Aucun plafond ne provoque d'exception.

## Service autonome

`perlecta serve` expose deux routes : `POST /analyses` (envoi multipart, champ `file`, réponse `rapport.en_dict()`) et `GET /version`. Sans état : rien n'est écrit, rien du contenu n'est journalisé, seule l'empreinte figure dans les journaux. Le plafond de taille est appliqué à la lecture du corps (`413`), avant toute analyse. Extra `service`, image `Dockerfile`.

## Limitations connues

- **Décodage des extraits.** Le texte révélé est décodé par la table ToUnicode de la police quand elle existe, sinon par l'encodage déclaré (WinAnsi, MacRoman), sinon approximativement en cp1252. Chaque anomalie porte la fiabilité (`decodage` : `tounicode`, `winansi`, `macroman`, `approx`, `inconnu`). Les détecteurs qui raisonnent sur les points de code (`CAR_INVISIBLES`, `HOMOGLYPHES`) ne lisent que le texte décodé de façon fiable. Une police CID sans ToUnicode donne un extrait vide avec `decodage: inconnu` et le nombre de glyphes.
- **Géométrie.** Les rectangles sont calculés à partir des largeurs de glyphes déclarées ou, pour les quatorze polices standard, de leurs métriques embarquées ; pour une police sans largeurs connues, la largeur est estimée. Les chemins de rognage (`W n`) et la boîte d'un XObject de forme ne sont pas appliqués.
- **Couleur.** Les espaces Separation et DeviceN hors `/Black` et `/All`, les motifs et les ombrages donnent une couleur inconnue : `PDF_COULEUR_FOND` ne conclut pas. Un fond porté par une image n'est pas lu.
- **Occultation.** Un rectangle plein compte, et une image à trois conditions : tracée après le texte, le couvrant entièrement, et ne faisant pas la page. Il faut en outre que la page porte du texte qu'aucune image ne couvre, c'est-à-dire que le recouvrement soit sélectif. Une image de page entière posée sur du texte échappe donc à `PDF_OCCULTATION` : sans lire les pixels, elle n'est pas distinguable de l'image d'un document numérisé. `PDF_DIVERGENCE_RENDU` couvre ce cas, et lui seul. Un chemin non rectangulaire, une opacité partielle ou un masque doux ne concluent pas.
- **Couche de reconnaissance optique.** Un document numérisé porte l'image de sa page et, par-dessus, le texte reconnu en mode de rendu invisible : c'est ainsi que tout scanner rend un document cherchable. `PDF_RENDU_INVISIBLE` écarte donc un segment invisible entièrement couvert par une image de page entière, sans quoi la quasi-totalité des pièces numérisées serait déclarée majeure.

  L'écart n'est jamais muet : la page ressort sous `PDF_COUCHE_NUMERISEE`, mineure, une par page, portant le texte de la couche et `verifiee_par_le_rendu: false`. Le segment reste par ailleurs non attribué, donc `PDF_DIVERGENCE_RENDU` le reprend ; quand cette comparaison a confronté la page à son image, la mineure disparaît. C'est le signal de fin : un appelant qui relance une analyse non confinée pour obtenir la comparaison sait ainsi qu'il l'a obtenue.

  Un document qui imite cette signature pour y cacher autre chose n'est donc révélé que par la comparaison. Sous `analyser_confine`, elle est impossible par construction : le sous-processus a `RLIMIT_FSIZE` à zéro et tesseract passe par des fichiers temporaires. Un appelant qui veut la verdict complète analyse en deux passes — `analyser_confine` pour tout, puis `analyser()` dans un conteneur qui confine autrement, pour les seules pièces portant une couche non vérifiée.
- **Rendu.** `PDF_DIVERGENCE_RENDU` demande l'extra `rendu` et le programme `tesseract`. Sous `analyser_confine`, le sous-processus n'a ni le programme dans son chemin ni le droit d'écrire les fichiers temporaires de tesseract : le détecteur y est ignoré avec son motif. Il ne s'exécute que par `analyser()` dans un conteneur qui confine autrement.
- **Formulaires et annotations.** Les flux d'apparence des champs de formulaire et des annotations ne sont pas analysés pour le texte masqué ; leurs actions le sont.
- **Courriel.** Les pièces jointes d'un courriel ne sont pas analysées à leur tour ; l'intégrateur les soumet séparément. Les feuilles de style ne sont lues que pour leurs règles simples (balise, classe, identifiant).
- **Word.** Les révisions insérées non acceptées sont affichées par Word et ne sont pas signalées ; seules les suppressions le sont. Les cadres hors zone imprimable ne sont pas analysés.
- **Hors périmètre.** XLSX, images, et la stéganographie à tout format.

## Intégration

Gelez ce contrat par un test chez vous : si un champ change de nom ou de type, votre test doit casser avant votre production. Le test `tests/test_contrat.py` de Perlecta en est le modèle.
