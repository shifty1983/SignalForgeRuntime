# SignalForge Canonical Options Backfill Multi-Manifest Research Export Bridge
# Paste this into QuantConnect Research.
#
# Set MANIFEST_KEYS from local signalforge_qc_canonical_backfill_manifest_keys.txt.
# This reads many small ObjectStore items and prints throttled encoded chunks.

from AlgorithmImports import *
import base64
import gzip
import hashlib
import json
import time


MANIFEST_KEYS = [
    # "PASTE_MANIFEST_KEYS_HERE"
]

CHARS_PER_PRINT_CHUNK = 5000
SLEEP_EVERY_N_CHUNKS = 10
SLEEP_SECONDS = 1.25


qb = QuantBook()


def read_object_store_text(key):
    if not qb.ObjectStore.ContainsKey(key):
        raise ValueError("ObjectStore key not found: " + key)
    return qb.ObjectStore.Read(key)


def build_export_payload(manifest_keys):
    exports = []
    errors = []

    for manifest_key in manifest_keys:
        try:
            manifest = json.loads(read_object_store_text(manifest_key))
            part_payloads = []

            for key in manifest.get("part_keys", []):
                part_payloads.append({
                    "object_store_key": key,
                    "part": json.loads(read_object_store_text(key)),
                })

            exports.append({
                "manifest_key": manifest_key,
                "manifest": manifest,
                "part_payloads": part_payloads,
            })

        except Exception as exc:
            errors.append({
                "manifest_key": manifest_key,
                "error": str(exc),
            })

    return {
        "artifact_type": "signalforge_canonical_options_backfill_multi_research_export_payload",
        "manifest_key_count": len(manifest_keys),
        "export_count": len(exports),
        "error_count": len(errors),
        "exports": exports,
        "errors": errors,
    }


def emit_large_payload(payload):
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    compressed = gzip.compress(raw)
    encoded = base64.b64encode(compressed).decode("ascii")
    sha = hashlib.sha256(compressed).hexdigest()

    chunks = [
        encoded[i:i + CHARS_PER_PRINT_CHUNK]
        for i in range(0, len(encoded), CHARS_PER_PRINT_CHUNK)
    ]

    print("SIGNALFORGE_CANONICAL_BACKFILL_MULTI_EXPORT_BEGIN")
    print("encoding=json+gzip+base64")
    print("compressed_sha256=" + sha)
    print("chunk_count=" + str(len(chunks)))
    print("encoded_char_count=" + str(len(encoded)))

    for idx, chunk in enumerate(chunks, start=1):
        print("SIGNALFORGE_CANONICAL_BACKFILL_MULTI_EXPORT_CHUNK " + str(idx).zfill(6) + " " + chunk)
        if SLEEP_EVERY_N_CHUNKS > 0 and idx % SLEEP_EVERY_N_CHUNKS == 0:
            time.sleep(SLEEP_SECONDS)

    print("SIGNALFORGE_CANONICAL_BACKFILL_MULTI_EXPORT_END")


print("SIGNALFORGE_MULTI_EXPORT_DISCOVERY")
print("manifest_key_count:", len(MANIFEST_KEYS))

payload = build_export_payload(MANIFEST_KEYS)

print("export_count:", payload["export_count"])
print("error_count:", payload["error_count"])

emit_large_payload(payload)
