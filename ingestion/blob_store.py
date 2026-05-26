"""Object storage for imaging pixel data.

Filesystem-backed for local/dev (root from BLOB_STORE_DIR); the interface is what
matters — production swaps in S3 behind the same put/get. Domain objects only ever
hold a URI to the blob, never the bytes.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


class FilesystemBlobStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("BLOB_STORE_DIR", "./blobs"))
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes) -> str:
        """Store bytes under key; return a resolvable URI."""
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path.resolve().as_uri()  # file://...

    def get(self, uri: str) -> bytes:
        return Path(unquote(urlparse(uri).path)).read_bytes()
