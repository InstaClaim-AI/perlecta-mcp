"""Command-line interface. The demonstration tool: one file, one command."""

from __future__ import annotations

import argparse
import json
import sys

from perlecta.confinement import analyser_confine
from perlecta.contrat import Gravite
from perlecta.moteur import VERSION_MOTEUR
from perlecta.reglage import CORPUS_DEFAUT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="perlecta",
        description="Reveals content that is present in a document but invisible on screen.",
    )
    parser.add_argument("--version", action="version", version=f"perlecta {VERSION_MOTEUR}")
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser("analyze", help="analyze a document and show what it hides")
    analyze.add_argument("file", help="the document to analyze")
    analyze.add_argument("--corpus", default=CORPUS_DEFAUT, help="corpus version (%(default)s)")
    analyze.add_argument("--json", action="store_true", help="print the raw report as JSON")

    serve = commands.add_parser("serve", help="stateless HTTP service")
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (%(default)s)")
    serve.add_argument("--port", type=int, default=8123, help="port to listen on (%(default)s)")
    serve.add_argument("--corpus", default=CORPUS_DEFAUT, help="corpus version (%(default)s)")

    mcp = commands.add_parser("mcp", help="local MCP server over standard input and output")
    mcp.add_argument(
        "--root",
        dest="roots",
        action="append",
        default=[],
        metavar="DIR",
        help="directory the server may read, repeatable; defaults to PERLECTA_MCP_ROOTS. "
        "Without a root, the server refuses to start",
    )
    mcp.add_argument("--corpus", default=CORPUS_DEFAUT, help="corpus version (%(default)s)")

    arguments = parser.parse_args(argv)
    if arguments.command == "serve":
        try:
            from perlecta.service import servir
        except ImportError as err:
            print(err)
            return 2
        return servir(arguments.host, arguments.port, arguments.corpus)
    if arguments.command == "mcp":
        try:
            from perlecta.serveur_mcp import servir_mcp
        except ImportError as err:
            # standard output is the protocol channel: nothing else is written there
            print(err, file=sys.stderr)
            return 2
        return servir_mcp(arguments.roots, arguments.corpus)
    return _analyze(arguments.file, arguments.corpus, arguments.json)


def _analyze(path: str, corpus: str, raw: bool) -> int:
    rapport = analyser_confine(path, version_corpus=corpus)

    if raw:
        print(json.dumps(rapport.en_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"Document     {path}")
    print(f"Type         {rapport.type_detecte}")
    print(f"Fingerprint  {rapport.empreinte}")
    print(f"Summary      {rapport.synthese.value}")
    if rapport.tronque:
        print("Partial analysis: a cap was reached.")
    for ignore in rapport.detecteurs_ignores:
        print(f"  not run  {ignore.nom} — {ignore.motif}")
    print()
    if not rapport.anomalies:
        print("No anomaly detected by the detectors that ran.")
        print("This does not mean the document is harmless.")
        return 0
    for number, anomalie in enumerate(rapport.anomalies, start=1):
        mark = "!!" if anomalie.gravite is Gravite.MAJEURE else " ."
        emplacement = anomalie.emplacement
        if emplacement.page:
            where = f"page {emplacement.page}"
        elif emplacement.partie:
            where = emplacement.partie
        else:
            where = "—"
        print(f"{mark} [{number}] {anomalie.code}  {where}")
        print(f"     {anomalie.explication}")
        print("     revealed content, not interpreted:")
        for line in anomalie.extrait.splitlines() or [""]:
            print(f"       | {line}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
