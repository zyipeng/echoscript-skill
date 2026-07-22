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
    print(json.dumps({
        "ok": True,
        "asr_detection": {
            "empty_action": no_model["recommended_action"],
            "existing_model_action": existing_model["recommended_action"],
        },
        "ingest_manifest": str(ingest_dir / "source.json"),
        "chunk_index": str(chunks_dir / "index.json"),
        "exports": [str(path) for path in sorted(exports.iterdir())],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
