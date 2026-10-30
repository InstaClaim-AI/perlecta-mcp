"""Detection du type par signature, jamais par extension."""

from __future__ import annotations

SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"\xd0\xcf\x11\xe0", "application/x-ole-storage"),
    (b"{\\rtf", "application/rtf"),
    (b"%!PS", "application/postscript"),
)

_ENTETES_COURRIEL = (b"from:", b"received:", b"return-path:", b"message-id:", b"mime-version:")


def detecter(octets: bytes) -> str:
    debut = octets[:1024]
    for signature, type_mime in SIGNATURES:
        if debut.startswith(signature):
            return type_mime
    # un PDF peut porter quelques octets de preambule avant %PDF-
    if b"%PDF-" in debut[:512]:
        return "application/pdf"
    minuscules = debut.lower()
    if any(minuscules.startswith(e) for e in _ENTETES_COURRIEL):
        return "message/rfc822"
    try:
        debut.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain"
