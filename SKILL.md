---
name: echoscript
description: Turn YouTube, Bilibili, Xiaoyuzhou podcast links, local audio/video, or subtitle files into timestamped transcripts and polished Chinese content. Use when Codex needs to acquire available subtitles or audio, detect and use local FunASR or MLX speech models without an external model API, translate English transcripts into Chinese, proofread transcripts, create quick summaries/detailed summaries/topic ideas, or export only the selected Markdown, Word DOCX, or PDF deliverables.
---

# EchoScript

Run a local-first media-to-document workflow. Use deterministic scripts for acquisition, ASR, chunking, and export. Perform translation, proofreading, and summarization directly with the current Agent's language ability; do not invoke another model through curl, HTTP, an SDK, or an external model endpoint.

## Keep the phase-one boundary

- Do not call an external LLM API for translation, proofreading, or summaries. Perform these text operations directly in the current Agent response/workspace.
- Prefer existing subtitles; run local ASR only when no usable transcript exists.
- Detect local ASR runtimes and model files before suggesting any download. Reuse a ready local FunASR or MLX model instead of downloading another model.
- Do not ask for an ASR API key. If no local ASR model exists, offer FunASR SenseVoiceSmall first, explain the download, and request approval before running `local_asr.py setup`.
- Do not upload to Notion, Feishu, or any other cloud destination in this version. Cloud storage is a later phase after local testing.
- Never borrow browser cookies or a signed-in browser session without explicit approval for that exact source.

## 1. Resolve deliverables and inspect capabilities

Resolve the requested export formats before doing the long-running work:

- If the user already named Markdown, Word/DOCX, PDF, or any combination, record exactly that selection and do not ask again.
- If the user did not name a format, ask one concise question: `最终需要 Markdown、Word 还是 PDF？可以多选。`
- Never default to all three formats. Generate only the selected deliverables; `document.md` may still exist as an internal canonical working file.

Run:

```bash
python3 scripts/media_ingest.py doctor
python3 scripts/local_asr.py doctor
```

Use absolute paths for the skill scripts and user files when the current working directory is not the skill directory.

## 2. Acquire the source

Create a dedicated output directory, then run:

```bash
python3 scripts/media_ingest.py ingest "SOURCE" --output-dir "/absolute/output/job"
```

The command writes `source.json` and, when subtitles are available, `transcript.raw.json`. If subtitles are unavailable, it downloads or references an audio file and records its path in `source.json`.

Platform behavior and permission-sensitive fallbacks are in [references/platforms.md](references/platforms.md). Read it before using a browser session or diagnosing a platform failure.

## 3. Detect, then transcribe locally only when needed

If `transcript.raw.json` already exists, skip ASR. Otherwise inspect the JSON from:

```bash
python3 scripts/local_asr.py doctor
```

Follow `recommended_action` exactly:

- If `ready` is `true` and `requires_quality_confirmation` is `false`, use the selected local backend without downloading anything.
- If `requires_quality_confirmation` is `true`, show `quality_warning` and offer the preferred FunASR download. Do not use a smoke-test-only model for a real transcript without explicit user acceptance.
- If a local model exists but its runtime is missing, request approval only to install the runtime; use the returned `setup_command`, which includes `--skip-model-download`.
- If no local ASR model exists, tell the user that the preferred download is FunASR `iic/SenseVoiceSmall` plus its VAD component and that the main model is about 1 GB. Run the returned setup command only after explicit approval.

After the detector reports `ready: true`, run:

```bash
python3 scripts/local_asr.py transcribe "/absolute/output/job" \
  --output "/absolute/output/job/transcript.raw.json"
```

Auto selection prefers a ready FunASR installation, then a ready cached MLX model. Do not force a FunASR download when another compatible local model is already ready.

`whisper-tiny` is smoke-test-only. After the user explicitly accepts its quality risk, allow it with:

```bash
python3 scripts/local_asr.py transcribe "/absolute/output/job" \
  --output "/absolute/output/job/transcript.raw.json" \
  --model mlx-community/whisper-tiny-mlx \
  --allow-low-quality-model
```

To select another already-cached model explicitly, pass `--backend mlx --model MODEL_ID` or `--backend funasr --model MODEL_ID`. The command still refuses uncached weights instead of downloading them.

After download approval, the default setup installs the local FunASR runtime and only the missing model components:

```bash
python3 scripts/local_asr.py setup --backend funasr
```

Never run setup speculatively. `transcribe` must fail with an actionable message instead of silently downloading weights.

If the selected cached backend is MLX and macOS reports `No Metal device available` inside a restricted sandbox, rerun the same local transcription command with host permission so MLX can access the Apple GPU. Do not change to an external API fallback.

## 4. Process text with the Agent

For a long transcript, split it without breaking timestamped segments. The default is language-aware: 8,000 characters for CJK transcripts and 12,000 for other languages.

```bash
python3 scripts/chunk_transcript.py "/absolute/output/job/transcript.raw.json" \
  --output-dir "/absolute/output/job/chunks"
```

Read [references/processing.md](references/processing.md) before proofreading, translating, or summarizing. Follow its evidence rules and output structure.

Inspect `transcript.raw.json` before processing, then use this checklist:

1. Read the `language`, `model`, and `quality_tier` fields and the source metadata.
2. Proofread in the source language while preserving meaning, timestamps, speaker labels, and uncertainty markers.
3. If `quality_tier` is `smoke-test-only`, use show notes only as spelling/topic hints. Never reconstruct missing speech from the description; retain uncertainty markers.
4. If the transcript language is English, translate the proofread version into natural Chinese. If it is Chinese, skip translation and remove the entire translation section. Do not translate other languages unless requested.
5. Process every chunk in `index.json` order and verify processed chunk count equals `chunk_count` before synthesis.
6. Generate separate `快速摘要`, `详细总结`, and `灵感选题` sections from the complete proofread or translated text.
7. Assemble `document.md` from [assets/document-template.md](assets/document-template.md). Omit sections that do not apply; do not leave any `{{...}}` placeholders.

Do not silently summarize only the first chunks. Use the compact coverage checklist in [references/processing.md](references/processing.md); do not rely on memory alone.

## 5. Export and verify documents

Run:

```bash
python3 scripts/document_export.py export "/absolute/output/job/document.md" \
  --output-dir "/absolute/output/job/exports" \
  --formats "SELECTED_FORMATS"

python3 scripts/document_export.py validate "/absolute/output/job/exports"
```

Use a comma-separated selection such as `md`, `docx`, `pdf`, or `docx,pdf`. The exporter requires this argument and rejects unresolved template placeholders. It uses `python-docx` for Word and ReportLab with an embedded local CJK font for PDF.

Visually render and inspect DOCX or PDF only when that format was selected and document tools are available. Fix clipped text, broken CJK glyphs, spacing, table, or pagination defects before delivery.

## 6. Report completion

Return:

- title, platform, source URL or local filename, and detected language;
- whether the transcript came from subtitles or local ASR;
- which of proofreading, English-to-Chinese translation, and the three summary sections were completed;
- clickable links or absolute paths only for the formats the user selected;
- the export-directory path and, as an optional convenience, `open "/path/to/exports"` on macOS;
- any explicit limitation, such as YouTube access restrictions or locally unclear audio.

Do not open Finder or another GUI unless the user asks. Do not claim a format exists until validation passes. Do not mention Notion or Feishu unless the user asks about the deferred second phase.
