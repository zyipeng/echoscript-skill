---
name: echoscript
description: Turn YouTube, Bilibili, Xiaoyuzhou podcast links, local audio/video, or subtitle files into timestamped transcripts and polished Chinese content. Use when an AI coding agent needs to acquire subtitles or audio, detect and use local FunASR or MLX speech models without an external model API, translate English transcripts into Chinese, proofread transcripts, create quick summaries/detailed summaries/topic ideas, or export only the selected Markdown, Word DOCX, or PDF deliverables.
---

# EchoScript

Run a local-first media-to-document workflow. Use the bundled scripts for acquisition, ASR, chunking, and export. Perform proofreading, translation, and summarization with the current Agent; never call another LLM through HTTP, an SDK, or an external model endpoint.

## Context and phase boundaries

- During a normal run, do not read `README.md` or any `scripts/*.py` source. Execute the documented commands. Inspect only the relevant script after a command fails and its diagnostic is insufficient.
- Do not read the full `transcript.raw.json`; it duplicates chunk content. Read `chunks/index.json` and the needed chunk files.
- Load [references/platforms.md](references/platforms.md) only after ingest fails or before requesting browser-session access.
- Prefer existing subtitles. Run local ASR only when no usable transcript exists.
- Detect local ASR files before suggesting a download. Offer FunASR SenseVoiceSmall first only when no suitable local model exists, and request approval before setup.
- Do not upload to Notion, Feishu, or another cloud destination in this phase.
- Never borrow browser cookies or a signed-in session without explicit permission for that source.

Resolve the directory containing this `SKILL.md` as the Skill directory. Run bundled scripts from that directory or use their absolute paths; never assume the current project is the Skill directory.

## 1. Resolve content and export scope

Infer selections already present in the request; do not ask twice.

- `summary-only`: metadata plus `快速摘要`, `详细总结`, and `灵感选题`; omit full transcript and translation.
- `full-transcript`: the three summary sections plus the complete proofread transcript; add Chinese translation only for English sources.
- If the user explicitly requests particular sections, include exactly those sections.
- Export only the selected `md`, `docx`, or `pdf` formats. Never default to all three.

If either choice is missing, ask one combined concise question covering only the missing choices, for example: `需要摘要版，还是包含完整校对文稿（英文附中文翻译）的完整版？导出 Markdown、Word 还是 PDF？可以多选。`

Run:

```bash
python3 scripts/media_ingest.py doctor
python3 scripts/local_asr.py doctor
```

Use absolute script and user-file paths when outside the Skill directory.

## 2. Acquire the source

Create a dedicated job directory and run:

```bash
python3 scripts/media_ingest.py ingest "SOURCE" --output-dir "/absolute/output/job"
```

This writes `source.json` and either `transcript.raw.json` or a local audio path. If ingest fails, then read [references/platforms.md](references/platforms.md) and follow only the relevant platform section.

## 3. Transcribe only when needed

Skip ASR when `transcript.raw.json` exists. Otherwise inspect the JSON from `local_asr.py doctor` and follow `recommended_action`:

- Reuse a ready local FunASR or MLX model.
- If model files exist but the runtime is missing, request approval to install only the runtime using the returned setup command.
- If no model exists, explain that the preferred FunASR `iic/SenseVoiceSmall` main model is about 1 GB, then run the returned setup command only after approval.
- If `requires_quality_confirmation` is true, show `quality_warning`. Never use a `smoke-test-only` model for a real transcript without explicit acceptance.

After the detector reports `ready: true`, run:

```bash
python3 scripts/local_asr.py transcribe "/absolute/output/job" \
  --output "/absolute/output/job/transcript.raw.json"
```

The command must refuse uncached weights rather than download silently. After approved FunASR setup, run `python3 scripts/local_asr.py setup --backend funasr`. Setup installs the full FunASR runtime including `torch`/`torchaudio`; readiness now requires them, so a model that imports but lacks torch is reported as not ready. For an explicitly accepted tiny model, add `--model mlx-community/whisper-tiny-mlx --allow-low-quality-model`.

For slow default-index downloads, users may export mirror variables before setup: `ECHOSCRIPT_PIP_INDEX_URL` (or `PIP_INDEX_URL`), `ECHOSCRIPT_PIP_EXTRA_INDEX_URL`, `ECHOSCRIPT_HF_ENDPOINT`. Setup streams install progress to stdout.

The transcribe result reports `timestamp_granularity`. When it is `coarse` (only a single whole-audio segment with no per-utterance timeline), a `timestamp_note` is included: any timestamps in the final document are approximate chapter navigation only and must be labeled as such in `处理说明`. Do not present coarse timestamps as precise per-sentence cues.

If a ready MLX model fails with `No Metal device available` in a restricted sandbox, rerun the same local command with host permission; do not switch to an external API.

## 4. Build a token-efficient evidence set

Merge adjacent same-speaker fragments by default (gap at most 2 seconds, paragraph span at most 30 seconds), then split at language-aware limits of 8,000 CJK or 12,000 other characters:

```bash
python3 scripts/chunk_transcript.py "/absolute/output/job/transcript.raw.json" \
  --output-dir "/absolute/output/job/chunks"
```

Use `--no-merge` only when exact source-segment boundaries are required. Read `chunks/index.json` for language, model, quality tier, counts, and coverage; do not reopen the raw JSON for the same data.

Choose one protocol:

- For `summary-only`, read [references/processing-summary.md](references/processing-summary.md). Use timestamped show notes as a navigation skeleton only when sufficiently detailed; validate claims against transcript evidence and fall back to full chunk coverage when the outline is sparse.
- For `full-transcript`, proofreading, or translation, read [references/processing-full.md](references/processing-full.md). Process every indexed chunk exactly once, save compact notes and processed text, synthesize from the notes, and concatenate processed chunks without rereading all raw chunks.

Never use show notes to reconstruct missing speech or as evidence for a quotation. Preserve uncertainty. If `quality_tier` is `smoke-test-only`, stop for confirmation before text processing.

Assemble `document.md` from [assets/document-template.md](assets/document-template.md). Remove unused sections and every unresolved `{{...}}` placeholder. A full transcript may merge timestamp fragments into natural paragraphs and remove only obvious ASR artifacts; never shorten meaningful passages merely because the summary repeats them, and never label deleted meaningful content as `[略]`.

## 5. Export and verify

```bash
python3 scripts/document_export.py export "/absolute/output/job/document.md" \
  --output-dir "/absolute/output/job/exports" \
  --formats "SELECTED_FORMATS"

python3 scripts/document_export.py validate "/absolute/output/job/exports"
```

Use a comma-separated selection such as `md`, `docx`, `pdf`, or `docx,pdf`. DOCX/PDF export needs `python-docx`, `pypdf`, and `reportlab`. The exporter auto-discovers a runtime in this order: `ECHOSCRIPT_DOCUMENT_PYTHON` → the skill's own `~/.cache/echoscript-skill/funasr-venv` (or `asr-venv`) → legacy Codex runtimes. If none are ready, it installs the packages into an existing skill venv (avoiding PEP 668 errors on system Python). Visually inspect DOCX or PDF only when selected and rendering tools are available. Fix clipping, broken CJK glyphs, spacing, tables, or pagination before delivery.

## 6. Report completion

Return the source metadata and language, subtitle/ASR origin, completed content sections, validated links only for selected formats, the export directory, and any concrete limitation. Do not open a GUI unless asked. Do not claim a file exists before validation passes. Do not mention deferred cloud sync unless the user asks.
