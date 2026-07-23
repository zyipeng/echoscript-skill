# Platform acquisition rules

Read this file when ingesting a URL, diagnosing acquisition, or considering browser-session access.

## Source order

Always prefer the least lossy and least privileged source:

1. Human-authored subtitles.
2. Platform auto-captions.
3. A publisher-provided transcript discovered through the matching podcast episode.
4. Public platform or publisher audio downloaded for local ASR.
5. A user-provided local audio/video file.
6. Manual transcript paste when a platform blocks all automated access.

Record the selected source in `source.json`. Never present auto-captions as human-authored subtitles.

## YouTube

- Use `yt-dlp` for public metadata, subtitles, and audio.
- Treat access as best-effort. A public page visible in a browser can still reject server-side extraction with bot or sign-in checks.
- When primary extraction fails, EchoScript automatically tries public YouTube oEmbed metadata. For podcast-like videos, it then requires a high-confidence Apple Podcasts episode-title match before using a publisher-linked transcript archive or the public podcast audio.
- Publisher archive downloads are size-limited, checked as ZIP files, and matched by episode title and release date. The selected archive member and source URL are recorded in `source.json`.
- Do not promise that every public video exposes a transcript.
- If neither YouTube nor a matching publisher source is available, offer local upload or manual transcript paste first.
- Use `--cookies-from-browser chrome` only after explicit approval. This reads the user's signed-in browser session for the exact operation.

Example after approval:

```bash
python3 scripts/media_ingest.py ingest "YOUTUBE_URL" \
  --output-dir "/absolute/output/job" \
  --cookies-from-browser chrome
```

## Bilibili

- Do not use `yt-dlp` as the Bilibili path; Bilibili frequently blocks it with HTTP 412.
- Use public Bilibili APIs for metadata, available captions, and signed DASH audio.
- Signed audio URLs expire. Download immediately and store only the local audio path in the durable manifest.
- If public captions are absent, use local ASR by default.
- `OpenCLI` may read subtitles through the user's current Chrome session. Pass `--allow-browser-session` only after explicit approval.

Example after approval:

```bash
python3 scripts/media_ingest.py ingest "BILIBILI_URL" \
  --output-dir "/absolute/output/job" \
  --allow-browser-session
```

## Xiaoyuzhou

- Accept only HTTPS episode URLs on `xiaoyuzhoufm.com` or `www.xiaoyuzhoufm.com`.
- Accept audio only from the known `media.xyzcdn.net` host.
- Reject credentials, custom ports, non-episode paths, untrusted redirects, and untrusted audio hosts.
- Xiaoyuzhou normally has no platform transcript; download audio and use local ASR.

## Local files

- Accept common audio/video formats and `.vtt`, `.srt`, `.txt`, or `.md` transcript files.
- Reference the original media path instead of copying large local files into the skill directory.
- Do not alter the original file.
- Use `ffprobe` to validate media and duration before ASR.
- Run `local_asr.py doctor` before any ASR setup. Reuse a detected local model; when none exists, offer FunASR SenseVoiceSmall as the first download choice.
- FunASR runs locally on CPU. Reuse a previously cached MLX model when it passes the quality gate; `whisper-tiny` requires a warning and explicit acceptance because it is smoke-test-only.
- MLX Whisper needs Metal access on Apple Silicon. A sandboxed `No Metal device available` error means the same command must be rerun with host permission; it does not require an API key.

## Failure language

Distinguish these states:

- `字幕不可用`: no usable subtitle track was exposed.
- `平台访问受限`: the platform rejected automated access.
- `音频获取失败`: metadata worked but the audio transfer failed.
- `本地转写未配置`: no ready local FunASR or MLX model/runtime pair was detected.
- `文稿部分不确定`: audio was processed, but unclear spans remain.

Never collapse all five into a generic "transcription failed" message.
