#!/usr/bin/env python3
"""Run a deterministic local smoke test for EchoScript scripts and document export."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def run_json(command: list[str], env: dict[str, str] | None = None) -> dict:
    result = subprocess.run(command, check=True, text=True, capture_output=True, env=env)
    return json.loads(result.stdout)


def run_failure(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode == 0:
        raise RuntimeError("command unexpectedly succeeded")
    return result.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description="EchoScript local self-test")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    output = Path(args.output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("self-test requires ffmpeg")
    audio = output / "sample.wav"
    run([
        ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=1", "-ar", "16000", "-ac", "1", str(audio),
    ])
    ingest_dir = output / "local-ingest"
    run([sys.executable, str(root / "media_ingest.py"), "ingest", str(audio), "--output-dir", str(ingest_dir)])

    isolated = output / "asr-detection"
    empty_env = os.environ.copy()
    empty_env.update({
        "HF_HOME": str(isolated / "huggingface"),
        "MODELSCOPE_CACHE": str(isolated / "modelscope"),
        "ECHOSCRIPT_ASR_PYTHON": "",
        "ECHOSCRIPT_FUNASR_PYTHON": "",
        "ECHOSCRIPT_FUNASR_MODEL": "",
        "ECHOSCRIPT_FUNASR_VAD_MODEL": "",
    })
    no_model = run_json([
        sys.executable, str(root / "local_asr.py"), "doctor",
        "--cache-dir", str(isolated / "cache"),
    ], env=empty_env)
    if no_model["local_model_available"] or no_model["recommended_action"] != "offer_funasr_download":
        raise RuntimeError("ASR detector did not prefer FunASR when no local model was present")

    fake_main = isolated / "existing-funasr-main"
    fake_vad = isolated / "existing-funasr-vad"
    for model_dir in (fake_main, fake_vad):
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "config.yaml").write_text("model: fixture\n", encoding="utf-8")
        (model_dir / "model.pt").write_bytes(b"fixture")
    existing_env = empty_env.copy()
    existing_env.update({
        "ECHOSCRIPT_FUNASR_MODEL": str(fake_main),
        "ECHOSCRIPT_FUNASR_VAD_MODEL": str(fake_vad),
    })
    existing_model = run_json([
        sys.executable, str(root / "local_asr.py"), "doctor",
        "--cache-dir", str(isolated / "cache"),
    ], env=existing_env)
    if not existing_model["local_model_available"] or existing_model["recommended_action"] != "install_funasr_runtime":
        raise RuntimeError("ASR detector attempted a model download despite existing FunASR files")

    transcript = {
        "schema_version": 1,
        "language": "en",
        "transcript_kind": "fixture",
        "source": str(audio),
        "segment_count": 3,
        "segments": [
            {"start_ms": 0, "end_ms": 3200, "text": "Welcome to this short EchoScript test."},
            {"start_ms": 3200, "end_ms": 7600, "text": "The agent proofreads, translates, and summarizes the transcript."},
            {"start_ms": 7600, "end_ms": 11000, "text": "Documents are exported locally as Markdown, Word, and PDF."},
        ],
        "text": "Welcome to this short EchoScript test.\nThe agent proofreads, translates, and summarizes the transcript.\nDocuments are exported locally as Markdown, Word, and PDF.",
    }
    transcript_path = output / "transcript.raw.json"
    transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chunks_dir = output / "chunks"
    run([sys.executable, str(root / "chunk_transcript.py"), str(transcript_path), "--output-dir", str(chunks_dir), "--max-chars", "2000"])
    merged_index = json.loads((chunks_dir / "index.json").read_text(encoding="utf-8"))
    if merged_index["source_segment_count"] != 3 or merged_index["merged_segment_count"] != 1:
        raise RuntimeError("adjacent same-speaker transcript fragments were not merged")

    unmerged_chunks = output / "chunks-unmerged"
    run([
        sys.executable, str(root / "chunk_transcript.py"), str(transcript_path),
        "--output-dir", str(unmerged_chunks), "--max-chars", "2000", "--no-merge",
    ])
    unmerged_index = json.loads((unmerged_chunks / "index.json").read_text(encoding="utf-8"))
    if unmerged_index["merged_segment_count"] != 3 or unmerged_index["merge_enabled"]:
        raise RuntimeError("--no-merge did not preserve source segment boundaries")

    chinese_segments = [
        {"start_ms": 0, "end_ms": 1000, "speaker": 0, "text": "第一段"},
        {"start_ms": 1500, "end_ms": 2500, "speaker": 0, "text": "继续说明"},
        {"start_ms": 2600, "end_ms": 3500, "speaker": 1, "text": "另一位发言"},
    ]
    chinese_transcript = {
        **transcript,
        "language": "zh",
        "segments": chinese_segments,
        "segment_count": len(chinese_segments),
        "text": "\n".join(item["text"] for item in chinese_segments),
    }
    chinese_path = output / "transcript.zh.json"
    chinese_path.write_text(json.dumps(chinese_transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chinese_chunks = output / "chunks-zh"
    run([sys.executable, str(root / "chunk_transcript.py"), str(chinese_path), "--output-dir", str(chinese_chunks)])
    chinese_index = json.loads((chinese_chunks / "index.json").read_text(encoding="utf-8"))
    if chinese_index["max_chars"] != 8000:
        raise RuntimeError("CJK transcript did not use the 8000-character adaptive default")
    chinese_body = (chinese_chunks / "chunk-001.md").read_text(encoding="utf-8")
    if chinese_index["merged_segment_count"] != 2 or "第一段，继续说明" not in chinese_body:
        raise RuntimeError("CJK fragments were not joined into a natural paragraph")
    if chinese_body.count("[说话人") != 2:
        raise RuntimeError("speaker changes were not preserved during fragment merging")

    document = output / "document.md"
    document.write_text(
        """# EchoScript 本地测试

> 平台：本地文件  
> 作者：EchoScript  
> 原始来源：sample.wav

## 快速摘要

- 这是一次不调用外部模型 API 的本地工作流测试。
- 测试覆盖媒体检查、文稿分块和三种文档导出。

## 详细总结

测试先验证本地音频，再把带时间戳的文字稿分块。最终文档由 Markdown 生成 Word，并从同一 Word 版式生成 PDF。

## 灵感选题

| 标题 | 切入角度 | 证据时间点 |
| --- | --- | --- |
| Agent 如何完成播客整理 | 本地优先与隐私 | 00:00:03 |

## 校对后文字稿

[00:00:00] Welcome to this short EchoScript test.

[00:00:03] The agent proofreads, translates, and summarizes the transcript.

## 中文翻译

[00:00:00] 欢迎使用这次简短的 EchoScript 测试。

## 处理说明

- 文稿来源：测试夹具
- 处理步骤：校对 / 英译中 / 总结
- 局限与不确定内容：无
""",
        encoding="utf-8",
    )
    exports = output / "exports"
    run([sys.executable, str(root / "document_export.py"), "export", str(document), "--output-dir", str(exports), "--formats", "md,docx,pdf", "--name", "echoscript-self-test"])
    run([sys.executable, str(root / "document_export.py"), "validate", str(exports)])

    single_export = output / "single-format"
    run([sys.executable, str(root / "document_export.py"), "export", str(document), "--output-dir", str(single_export), "--formats", "docx", "--name", "word-only"])
    single_files = sorted(path.name for path in single_export.iterdir())
    if single_files != ["word-only.docx"]:
        raise RuntimeError(f"single-format export created unexpected files: {single_files}")

    unresolved = output / "unresolved.md"
    unresolved.write_text("# Invalid\n\n## 内容\n\n{{未替换内容}}\n", encoding="utf-8")
    placeholder_error = run_failure([
        sys.executable, str(root / "document_export.py"), "export", str(unresolved),
        "--output-dir", str(output / "invalid-export"), "--formats", "md",
    ])
    if "未替换占位符" not in placeholder_error:
        raise RuntimeError("exporter did not reject an unresolved template placeholder")
    print(json.dumps({
        "ok": True,
        "asr_detection": {
            "empty_action": no_model["recommended_action"],
            "existing_model_action": existing_model["recommended_action"],
        },
        "adaptive_chunk_chars": chinese_index["max_chars"],
        "segment_merge": {
            "source": merged_index["source_segment_count"],
            "merged": merged_index["merged_segment_count"],
            "speaker_boundaries_preserved": True,
        },
        "single_format_export": single_files,
        "placeholder_rejected": True,
        "ingest_manifest": str(ingest_dir / "source.json"),
        "chunk_index": str(chunks_dir / "index.json"),
        "exports": [str(path) for path in sorted(exports.iterdir())],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
