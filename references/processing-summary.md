# Summary-only protocol

Use this protocol only when the deliverable omits the complete transcript and translation. The transcript remains the authority; timestamped show notes are a navigation index, not factual evidence.

## Build and validate the outline

1. Read source metadata and extract timestamped topics from `source.json` description when present.
2. Treat the outline as sufficiently detailed only when it spans most of the episode and has no large unexplained timeline gaps. Otherwise process all chunks.
3. Map every outline topic to the corresponding indexed transcript range. Include the opening, closing, and transcript ranges covering gaps between outline entries.
4. Read enough transcript around each mapped point to establish the claim, example, speaker position, and conclusion. Expand the range whenever context is incomplete or conflicts with show notes.
5. Record compact evidence notes with timestamps; do not copy long raw passages.

For a detailed summary, favor coverage over an aggressive Token target. If selective reading would omit a topic or make a quotation uncertain, read the affected full chunk. Never claim full-transcript proofreading was completed in this mode.

## Evidence and quality rules

- Base claims and quotations on transcript evidence, not the description.
- Use show notes only for navigation, names, and topic labels that the transcript supports.
- Preserve quantities, negation, degree, disagreements, and uncertainty.
- Mark unclear evidence instead of reconstructing it.
- Stop for user confirmation when `quality_tier` is `smoke-test-only`.

## Output

- `快速摘要`: 3-6 concise bullets or paragraphs covering the subject, central question, major conclusion, and intended audience.
- `详细总结`: organize by topic; explain key arguments, examples, disagreements, and conclusions, with evidence timestamps.
- `灵感选题`: provide 5-10 evidence-backed ideas. For each include `标题`, `适合平台`, `切入角度`, `可引用观点或原话`, `延展思路`, and `证据时间点`.

Do not include transcript or translation headings. Do not fabricate quotations, strengthen opinions into facts, or predict virality. In processing notes, state that the result is summary-only and whether a timestamped outline was used for navigation.
