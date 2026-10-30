# Security policy

Perlecta analyzes documents chosen by an attacker, and its MCP server sits between those documents and an AI agent. A flaw in either is a security issue, and we treat it as one.

## Reporting a vulnerability

Please do not open a public issue. Report it privately through GitHub: open the **Security** tab of this repository, then **Report a vulnerability**.

Useful reports include:

- the document or the input that triggers the problem, or a script that builds it;
- what Perlecta does, and what it should have done;
- the version, as printed by `perlecta --version`.

Examples of what we consider vulnerabilities:

- any path through which text taken from an analyzed document reaches the output of the MCP server;
- a document that makes an analysis fail, hang or crash the caller instead of producing a report;
- a document that makes Perlecta execute, resolve, follow or fetch anything it contains;
- a way for the MCP server to read a file outside its declared roots.

A document that hides content Perlecta does not detect is a detection gap rather than a vulnerability: please open a regular issue, with the document if you can share it.

## Supported versions

Only the latest release receives fixes.
