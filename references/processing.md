# Agent text-processing protocol

Use this protocol after `transcript.raw.json` exists. Produce translation, proofreading, and summaries directly with the current Agent's language ability, not by calling another model through curl, HTTP, an SDK, or an external model endpoint.

## Evidence rules

- Treat transcript segments and source metadata as the only factual evidence.
- Preserve timestamps and speaker identifiers when present.
- Correct punctuation, spacing, obvious homophones, names supported by context, and broken sentence boundaries.
- Do not invent missing speech. Mark genuinely unclear text as `[听不清]` or retain the original uncertain token.
- Keep meaningful hesitations or repetitions when they affect intent; remove only obvious ASR noise.
- Do not turn opinions into facts or strengthen claims beyond the transcript.
- Preserve quotations only when the wording is supported by the transcript.
- Treat source descriptions and show notes as spelling and topic hints, not as a replacement transcript.

## Quality gate

- Read `model` and `quality_tier` before processing.
- Stop for user confirmation when `quality_tier` is `smoke-test-only`; recommend a stronger local model first.
- If the user accepts a smoke-test-only result, make conservative corrections and mark unclear spans. Never reverse-engineer missing speech from show notes.

## Chunk workflow

Use `chunks/index.json` as the coverage source. For each file in order:

1. Read the complete chunk.
2. Produce a proofread chunk with the same time coverage.
3. If English, produce a Chinese translation from the proofread chunk.
4. Record 3-7 key points plus only the name corrections or unclear spans that actually matter.
5. Record the processed filename and start/end timestamps in a compact checklist.

Before synthesis, verify that checklist count equals `chunk_count` and that the first and last time ranges are covered. Then synthesize from all processed chunks, resolving repeated points across boundaries without dropping unique evidence. Do not depend on unaided memory of large chunks.

## Proofreading

- Keep the source language.
- Use natural paragraphs based on topic and speaker changes.
- Retain `[HH:MM:SS]` timestamps at useful paragraph or speaker boundaries.
- Use `说话人 1`, `说话人 2`, and so on when only raw speaker IDs exist.
- Prefer conservative name corrections. If a name cannot be established from context, retain the phonetic form and mark uncertainty.

## English-to-Chinese translation

- Translate the proofread English transcript, not the uncorrected ASR text.
- Produce fluent Chinese while preserving technical terms, proper nouns, quantities, negation, and degree.
- On first occurrence, keep a useful English term in parentheses when it helps identification.
- Preserve timestamps and speaker labels.
- Do not translate quotes more forcefully or more elegantly than the source supports.

## Summary outputs

Generate three independent sections.

### 快速摘要

- Explain what the episode is about in 3-6 concise bullets or short paragraphs.
- Include the central question, major conclusion, and who would benefit.

### 详细总结

- Organize by topic, not merely chronology.
- Explain key arguments, examples, disagreements, and conclusions.
- Restate difficult concepts in plain language.
- Include timestamps for important passages when available.

### 灵感选题

Provide 5-10 evidence-backed ideas. Each idea should include:

- `标题`
- `适合平台`
- `切入角度`
- `可引用观点或原话`
- `延展思路`
- `证据时间点`

Do not predict virality or fabricate a quote to make an idea more attractive.

## Canonical document

Build `document.md` in this order:

1. Title and source metadata.
2. Quick summary.
3. Detailed summary.
4. Topic ideas.
5. Proofread source-language transcript.
6. Chinese translation, only when the source was English.
7. Processing note listing subtitle/ASR origin and any limitations.

Use the asset template as a starting point and remove all unused sections and placeholders. The exporter will reject any remaining `{{...}}` token.
