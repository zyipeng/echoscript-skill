# Full transcript protocol

Use this protocol when the deliverable contains a complete proofread transcript or translation. Read every indexed chunk once; show notes cannot replace transcript coverage.

## Evidence and quality rules

- Treat transcript segments and source metadata as factual evidence. Use source descriptions only for topic navigation and conservative spelling hints.
- Preserve meaning, quantities, negation, degree, timestamps, speaker changes, and uncertainty. Do not invent missing speech or strengthen claims.
- Mark genuinely unclear text as `[听不清]` or keep the uncertain original. Remove only unmistakable ASR artifacts or accidental duplicate fragments.
- Never delete meaningful transcript passages because the summary already covers them. Do not use `[略]` to conceal abridgement in a full transcript.
- Stop for user confirmation when `quality_tier` is `smoke-test-only`; recommend a stronger local model first.

## One-pass chunk workflow

Use `chunks/index.json` as the coverage ledger. For every file in order:

1. Read the raw chunk once.
2. Write its proofread result to a matching processed-chunk file with the same start/end coverage.
3. For English, translate that proofread result into Chinese in a matching translation file.
4. Write a compact evidence note containing 3-7 unique points, important names, only supported quotations, unclear spans, and the chunk time range.
5. Mark the chunk complete in a checklist.

Before synthesis, verify the checklist count equals `chunk_count`, first and last ranges are covered, and no indexed range is missing. Synthesize summaries from all compact notes. Reopen a processed chunk only to verify an exact quotation or resolve a conflict; do not reread all raw chunks. Assemble the full transcript and translation from saved processed files in index order.

## Proofreading and translation

- Keep the proofread transcript in its source language and group it into natural paragraphs.
- Keep one timestamp at each useful paragraph or speaker boundary rather than on every short ASR fragment.
- Preserve speaker IDs as `说话人 1`, `说话人 2`, and so on.
- Correct punctuation, spacing, obvious contextual homophones, and broken sentence boundaries conservatively.
- Translate the proofread English, not raw ASR. Produce natural Chinese while preserving technical terms, proper nouns, numbers, and claim strength.
- Retain a useful English term in parentheses on first occurrence when it aids identification.

## Summary sections

- `快速摘要`: 3-6 concise bullets or paragraphs covering the subject, central question, major conclusion, and intended audience.
- `详细总结`: organize by topic; cover key arguments, examples, disagreements, and conclusions with important timestamps.
- `灵感选题`: provide 5-10 evidence-backed ideas. For each include `标题`, `适合平台`, `切入角度`, `可引用观点或原话`, `延展思路`, and `证据时间点`.

Never fabricate quotations or predict virality. Build the canonical document in this order: metadata, quick summary, detailed summary, topic ideas, proofread transcript, Chinese translation only for English, and processing notes.
