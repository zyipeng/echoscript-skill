#!/usr/bin/env python3
"""Merge short transcript fragments, then split them into compact Markdown chunks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


class ChunkError(RuntimeError):
    pass


CJK_LANGUAGES = {"zh", "zh-cn", "zh-tw", "yue", "ja", "ko"}
TERMINAL_PUNCTUATION = set("。！？!?；;，,：:…")


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
    speaker = speaker_id(segment)
    prefix = f"[说话人 {speaker}] " if speaker else ""
    return f"[{timestamp}] {prefix}{str(segment.get('text') or '').strip()}".rstrip()


def speaker_id(segment: dict[str, Any]) -> str:
    for key in ("speaker", "speaker_id"):
        value = segment.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def contains_cjk(text: str) -> bool:
    return any("\u3400" <= character <= "\u9fff" for character in text)


def join_text(left: str, right: str, language: str) -> str:
    if not left:
        return right
    if not right:
        return left
    normalized = str(language or "unknown").lower().replace("_", "-")
    is_cjk = (
        normalized in CJK_LANGUAGES
        or normalized.startswith("zh-")
        or contains_cjk(left + right)
    )
    if is_cjk:
        separator = "" if left[-1] in TERMINAL_PUNCTUATION or right[0] in TERMINAL_PUNCTUATION else "，"
    else:
        separator = "" if left[-1].isspace() or right[0].isspace() else " "
    return f"{left}{separator}{right}"


def merge_segments(
    segments: list[dict[str, Any]], *, language: str, gap_ms: int, max_span_ms: int
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for raw in segments:
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        item = dict(raw)
        item["text"] = text
        item["start_ms"] = max(0, int(float(item.get("start_ms") or 0)))
        item["end_ms"] = max(item["start_ms"], int(float(item.get("end_ms") or item["start_ms"])))
        item["_source_segment_count"] = 1
        if merged:
            previous = merged[-1]
            gap = item["start_ms"] - previous["end_ms"]
            span = max(previous["end_ms"], item["end_ms"]) - previous["start_ms"]
            can_merge = (
                item["start_ms"] >= previous["start_ms"]
                and gap <= gap_ms
                and span <= max_span_ms
                and speaker_id(item) == speaker_id(previous)
            )
            if can_merge:
                previous["text"] = join_text(previous["text"], item["text"], language)
                previous["end_ms"] = max(previous["end_ms"], item["end_ms"])
                previous["_source_segment_count"] += 1
                continue
        merged.append(item)
    return merged


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
    parser.add_argument(
        "--merge-gap",
        type=float,
        default=2.0,
        help="Merge adjacent same-speaker segments when the gap is at most this many seconds (default: 2)",
    )
    parser.add_argument(
        "--max-span",
        type=float,
        default=30.0,
        help="Maximum duration in seconds for one merged paragraph (default: 30)",
    )
    parser.add_argument("--no-merge", action="store_true", help="Keep every source segment as a separate paragraph")
    args = parser.parse_args()
    try:
        source = Path(args.transcript).expanduser().resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        language = str(payload.get("language") or "unknown")
        max_chars = args.max_chars if args.max_chars is not None else default_max_chars(language)
        if max_chars < 2000:
            raise ChunkError("--max-chars 不能小于 2000")
        if args.merge_gap < 0:
            raise ChunkError("--merge-gap 不能小于 0")
        if args.max_span <= 0:
            raise ChunkError("--max-span 必须大于 0")
        segments = payload.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ChunkError("transcript JSON 没有可用 segments")
        source_segments = [item for item in segments if isinstance(item, dict) and str(item.get("text") or "").strip()]
        if args.no_merge:
            prepared_segments = [dict(item, _source_segment_count=1) for item in source_segments]
        else:
            prepared_segments = merge_segments(
                source_segments,
                language=language,
                gap_ms=round(args.merge_gap * 1000),
                max_span_ms=round(args.max_span * 1000),
            )
        chunks = chunk_segments(prepared_segments, max_chars)
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
                "source_segment_count": sum(int(item.get("_source_segment_count") or 1) for item in chunk),
                "start_ms": chunk[0].get("start_ms", 0),
                "end_ms": chunk[-1].get("end_ms", 0),
                "character_count": len(body),
                "status": "pending",
            })
        index_payload = {
            "schema_version": 1,
            "source": str(source),
            "language": language,
            "transcript_kind": payload.get("transcript_kind"),
            "model": payload.get("model"),
            "quality_tier": payload.get("quality_tier"),
            "max_chars": max_chars,
            "merge_enabled": not args.no_merge,
            "merge_gap_seconds": args.merge_gap,
            "max_span_seconds": args.max_span,
            "source_segment_count": len(source_segments),
            "merged_segment_count": len(prepared_segments),
            "chunk_count": len(index),
            "chunks": index,
        }
        (output_dir / "index.json").write_text(json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "ok": True,
            "language": language,
            "max_chars": max_chars,
            "merge_enabled": not args.no_merge,
            "source_segment_count": len(source_segments),
            "merged_segment_count": len(prepared_segments),
            "chunk_count": len(index),
            "index": str(output_dir / "index.json"),
        }, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, ChunkError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
