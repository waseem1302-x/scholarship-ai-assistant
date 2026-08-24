"""Restricted child-process entry point for Docling PDF conversion."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.modules.catalogue_ingestion.document_conversion_transport import FilesystemDoclingJobServer


def _convert(
    input_path: Path,
    *,
    enable_ocr: bool,
    max_pages: int,
    max_file_bytes: int,
    max_output_characters: int,
) -> str:
    # Imports are local so normal API/worker startup never loads Docling or its
    # ML stack.  No URL, credential, database, or application settings are
    # accepted by this process.
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    artifacts_path = os.environ.get("DOCLING_ARTIFACTS_PATH")
    if not artifacts_path or not Path(artifacts_path).is_dir():
        raise RuntimeError("reviewed_docling_artifacts_missing")
    options = PdfPipelineOptions()
    options.artifacts_path = Path(artifacts_path)
    options.do_ocr = enable_ocr
    options.do_table_structure = True
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    converted = converter.convert(
        input_path,
        max_num_pages=max_pages,
        max_file_size=max_file_bytes,
    )
    text = converted.document.export_to_markdown()
    if not isinstance(text, str) or len(text) > max_output_characters:
        raise ValueError("invalid_or_oversized_document_output")
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--job-root")
    parser.add_argument("--poll-milliseconds", type=int, default=100)
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-file-bytes", type=int)
    parser.add_argument("--max-output-characters", type=int)
    parser.add_argument("--enable-ocr", action="store_true")
    args = parser.parse_args()
    if args.serve:
        if not args.job_root or args.poll_milliseconds < 1:
            parser.error("--serve requires --job-root and a positive --poll-milliseconds")
        FilesystemDoclingJobServer(
            job_root=args.job_root,
            poll_interval_milliseconds=args.poll_milliseconds,
        ).serve_forever()
        return 0
    if not all(
        (args.input, args.output, args.max_pages, args.max_file_bytes, args.max_output_characters)
    ):
        parser.error("one-shot conversion requires input, output, and all conversion limits")
    text = _convert(
        Path(args.input),
        enable_ocr=args.enable_ocr,
        max_pages=args.max_pages,
        max_file_bytes=args.max_file_bytes,
        max_output_characters=args.max_output_characters,
    )
    Path(args.output).write_text(json.dumps({"text": text}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
