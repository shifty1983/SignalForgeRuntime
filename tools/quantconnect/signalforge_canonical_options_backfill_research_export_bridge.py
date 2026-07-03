# SignalForge Canonical Options Backfill ObjectStore Export Bridge
# Paste this into QuantConnect Research.
#
# 1. Set MANIFEST_KEY below.
# 2. Run notebook cell.
# 3. Copy all SIGNALFORGE_CANONICAL_BACKFILL_EXPORT_CHUNK lines.
# 4. Paste into local text file.
# 5. Decode locally.

from AlgorithmImports import *
import base64
import gzip
import hashlib
import json
import math


MANIFEST_KEY = "PASTE_MANIFEST_KEY_HERE"

CHARS_PER_PRINT_CHUNK = 6000


qb = QuantBook()


def read_object_store_text(key):
    if not qb.ObjectStore.ContainsKey(key):
        raise ValueError("ObjectStore key not found: " + key)
    return qb.ObjectStore.Read(key)


def emit_large_payload(payload):
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    compressed = gzip.compress(raw)
    encoded = base64.b64encode(compressed).decode("ascii")
    sha = hashlib.sha256(compressed).hexdigest()

    chunks = [
        encoded[i:i + CHARS_PER_PRINT_CHUNK]
        for i in range(0, len(encoded), CHARS_PER_PRINT_CHUNK)
    ]

    print("SIGNALFORGE_CANONICAL_BACKFILL_EXPORT_BEGIN")
    print("encoding=json+gzip+base64")
    print("compressed_sha256=" + sha)
    print("chunk_count=" + str(len(chunks)))
    print("encoded_char_count=" + str(len(encoded)))

    for idx, chunk in enumerate(chunks, start=1):
        print("SIGNALFORGE_CANONICAL_BACKFILL_EXPORT_CHUNK " + str(idx).zfill(6) + " " + chunk)

    print("SIGNALFORGE_CANONICAL_BACKFILL_EXPORT_END")


manifest_text = read_object_store_text(MANIFEST_KEY)
manifest = json.loads(manifest_text)

part_payloads = []
for key in manifest.get("part_keys", []):
    part_text = read_object_store_text(key)
    part = json.loads(part_text)
    part_payloads.append({
        "object_store_key": key,
        "part": part,
    })

export_payload = {
    "artifact_type": "signalforge_canonical_options_backfill_research_export_payload",
    "manifest_key": MANIFEST_KEY,
    "manifest": manifest,
    "part_payloads": part_payloads,
}

emit_large_payload(export_payload)
