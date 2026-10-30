"""Une table ToUnicode qui fabrique une demi-paire de substitution ne fait pas perdre le rapport.

Une plage bfrange dont la cible deborde dans U+D800-U+DFFF produisait un caractere
qui n'en est pas un. Le fils confine ne pouvait plus serialiser son rapport en
UTF-8, l'analyse echouait, et le texte invisible du meme document n'etait pas
rapporte.
"""

from __future__ import annotations

import json
from pathlib import Path

import pikepdf

from perlecta import analyser_confine
from perlecta.contrat import Synthese

_CMAP = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
2 beginbfrange
<0000> <0500> <D7FF>
<0600> <06FF> <0041>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""


def _pdf_a_demi_paire(chemin: Path) -> None:
    pdf = pikepdf.new()
    descendante = pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.CIDFontType2,
        BaseFont=pikepdf.Name.Foo,
        CIDSystemInfo=pikepdf.Dictionary(
            Registry=pikepdf.String("Adobe"), Ordering=pikepdf.String("Identity"), Supplement=0
        ),
        DW=500,
    )
    police = pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.Type0,
        BaseFont=pikepdf.Name.Foo,
        Encoding=pikepdf.Name("/Identity-H"),
        DescendantFonts=pikepdf.Array([pdf.make_indirect(descendante)]),
        ToUnicode=pdf.make_indirect(pikepdf.Stream(pdf, _CMAP)),
    )
    # mode de rendu 3 : du texte invisible, dont un code (0481) tombe dans la demi-paire
    contenu = b"BT /F1 12 Tf 3 Tr 72 700 Td <0600060106020481060306040605> Tj ET"
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 612, 792],
            Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=police)),
            Contents=pdf.make_stream(contenu),
        )
    )
    pdf.pages.append(page)
    pdf.save(chemin)


def test_le_texte_invisible_reste_rapporte(tmp_path: Path) -> None:
    chemin = tmp_path / "demi_paire.pdf"
    _pdf_a_demi_paire(chemin)
    rapport = analyser_confine(chemin.read_bytes())
    assert rapport.synthese is Synthese.MAJEURES
    assert "PDF_RENDU_INVISIBLE" in {a.code for a in rapport.anomalies}
    assert not any(d.nom == "*" for d in rapport.detecteurs_ignores)
    # le rapport se serialise en UTF-8, ce que fait le service autonome
    json.dumps(rapport.en_dict(), ensure_ascii=False).encode("utf-8")
