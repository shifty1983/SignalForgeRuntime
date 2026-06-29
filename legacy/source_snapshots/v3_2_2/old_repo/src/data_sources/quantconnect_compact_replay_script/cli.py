from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.data_sources.quantconnect_compact_replay_script.file_writer import (
    write_quantconnect_compact_replay_script_result,
)
from src.data_sources.quantconnect_compact_replay_script.script_builder import (
    DEFAULT_CLASS_NAME,
    DEFAULT_MANIFEST_OBJECT_STORE_KEY,
    DEFAULT_MANIFEST_MODULE_FILENAME,
    DEFAULT_SCRIPT_FILENAME,
    build_signalforge_quantconnect_compact_replay_script,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a QuantConnect Lean Python compact replay script from a SignalForge handoff manifest."
    )
    parser.add_argument(
        "--handoff-source",
        required=True,
        help="Path to SignalForge QuantConnect historical replay handoff JSON artifact.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument("--class-name", default=DEFAULT_CLASS_NAME)
    parser.add_argument("--script-filename", default=DEFAULT_SCRIPT_FILENAME)
    parser.add_argument("--manifest-object-store-key", default=DEFAULT_MANIFEST_OBJECT_STORE_KEY)
    parser.add_argument("--manifest-module-filename", default=DEFAULT_MANIFEST_MODULE_FILENAME)
    parser.add_argument(
        "--external-manifest-module",
        action="store_true",
        help="Write replay manifest to a supplemental QuantConnect Python module instead of embedding it in main.py.",
    )
    parser.add_argument(
        "--compressed-inline-manifest",
        action="store_true",
        help="Embed the replay manifest as compressed base64 inside main.py.",
    )
    parser.add_argument(
        "--no-embed-manifest",
        action="store_true",
        help="Do not embed the replay manifest in the generated script; require Object Store manifest input instead.",
    )

    args = parser.parse_args(argv)

    result = build_signalforge_quantconnect_compact_replay_script(
        handoff_source=_read_json(args.handoff_source),
        class_name=args.class_name,
        script_filename=args.script_filename,
        manifest_object_store_key=args.manifest_object_store_key,
        embed_manifest=not args.no_embed_manifest,
        external_manifest_module=args.external_manifest_module,
        compressed_inline_manifest=args.compressed_inline_manifest,
        manifest_module_filename=args.manifest_module_filename,
    )
    summary = write_quantconnect_compact_replay_script_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if result.get("is_ready") else 1


def _read_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
