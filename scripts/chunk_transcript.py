#!/usr/bin/env python3
"""Split a normalized EchoScript transcript without breaking timestamped segments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


class ChunkError(RuntimeError):
    pass


CJK_LANGUAGES = {"zh", "zh-cn", "zh-tw", "yue", "ja", "ko"}


def default_max_chars(language: str) -> int:
    normalized = str(language or "unknown").lower().replace("_", "-")
    return 8000 if normalized in CJK_LANGUAGES or normalized.startswith("zh-") else 12000


def format_timestamp(milliseconds: Any) -> str:
    total = max(0, int(float(milliseconds or 0) // 1000))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def segment_line(segment: dict[str, Any]) -> str:
    timestamp = format_timestamp(segment.get("start_ms"))
    speaker = str(segment.get("speaker") or segment.get("speaker_id") or "").strip()
    prefix = f"[说话人 {speaker}] " if speaker else ""
    return f"[{timestamp}] {prefix}{str(segment.get('text') or '').strip()}".rstrip()


def chunk_segments(segments: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        size = len(segment_line(segment)) + 1
        if current and current_size + size > max_chars:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(segment)
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Split normalized transcript JSON into Markdown chunks")
    parser.add_argument("transcript")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--max-chars",
        type=int,
        help="Maximum characters per chunk; defaults to 8000 for CJK and 12000 otherwise",
    )
    args = parser.parse_args()
    try:
        source = Path(args.transcript).expanduser().resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        language = str(payload.get("language") or "unknown")
        max_chars = args.max_chars if args.max_chars is not None else default_max_chars(language)
        if max_chars < 2000:
            raise ChunkError("--max-chars 不能小于 2000")
        segments = payload.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ChunkError("transcript JSON 没有可用 segments")
        chunks = chunk_segments(segments, max_chars)
        if not chunks:
            raise ChunkError("文字稿没有可分块内容")
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        index: list[dict[str, Any]] = []
        for number, chunk in enumerate(chunks, start=1):
            name = f"chunk-{number:03d}.md"
            path = output_dir / name
            body = "\n\n".join(segment_line(item) for item in chunk) + "\n"
            path.write_text(body, encoding="utf-8")
            index.append({
                "number": number,
                "file": name,
                "segment_count": len(chunk),
                "start_ms": chunk[0].get("start_ms", 0),
                "end_ms": chunk[-1].get("end_ms", 0),
                "character_count": len(body),
                "status": "pending",
            })
        index_payload = {
            "schema_version": 1,
            "source": str(source),
            "language": language,
            "max_chars": max_chars,
            "chunk_count": len(index),
            "chunks": index,
        }
        (output_dir / "index.json").write_text(json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "ok": True,
            "language": language,
            "max_chars": max_chars,
            "chunk_count": len(index),
            "index": str(output_dir / "index.json"),
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, ChunkError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
