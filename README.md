# EchoScript Skill

[中文](#中文) · [English](#english)

EchoScript is a local-first Codex Skill that turns media links or local audio into polished transcripts, Chinese translations, summaries, and shareable documents.

---

## 中文

### 功能

EchoScript 可以处理：

- YouTube 视频链接
- 哔哩哔哩视频链接
- 小宇宙播客链接
- 本地音频、视频、字幕或文字稿文件

完整工作流包括：

1. 获取平台已有字幕或公开音频。
2. 没有字幕时，检测并调用本地 ASR 模型转写。
3. 由当前 Codex Agent 完成文字稿校对、英文翻译成中文和内容总结。
4. 分别生成 `快速摘要`、`详细总结` 和 `灵感选题`。
5. 导出 Markdown、Word DOCX 和 PDF。

翻译、校对和总结不接入外部 LLM API。Notion 和飞书同步暂未实现，计划在本地流程验证稳定后作为第二阶段功能加入。

### 安装

需要 Python 3、FFmpeg、FFprobe、curl 和 yt-dlp。安装到 Codex Skills 目录：

```bash
git clone https://github.com/zyipeng/echoscript-skill.git ~/.codex/skills/echoscript
```

安装后新建一个 Codex 任务，使用 `$echoscript` 调用。

如果只需要检查本机依赖：

```bash
python3 ~/.codex/skills/echoscript/scripts/media_ingest.py doctor
python3 ~/.codex/skills/echoscript/scripts/local_asr.py doctor
```

### 使用示例

在 Codex 中输入：

```text
用 $echoscript 处理这个 YouTube 链接。校对文稿，如果是英文就翻译成中文，
生成快速摘要、详细总结和灵感选题，最后导出 Markdown、Word 和 PDF。
```

也可以提供本地文件：

```text
用 $echoscript 处理 /absolute/path/to/podcast.mp3，并输出中文文稿和三种文档格式。
```

### 本地 ASR 规则

EchoScript 不会在转写时静默下载模型：

1. 先检查本机已有的 FunASR 和 MLX 模型。
2. 如果已有可用模型，直接复用。
3. 如果只有模型、没有运行环境，只提示安装运行环境，不重复下载模型。
4. 如果没有任何本地 ASR 模型，优先提供 FunASR `iic/SenseVoiceSmall` 下载选项。
5. 下载模型前必须先获得用户许可。

检测命令：

```bash
python3 scripts/local_asr.py doctor
```

获得下载许可后，安装首选 FunASR 后端：

```bash
python3 scripts/local_asr.py setup --backend funasr
```

转写命令会自动选择已经就绪的本地后端：

```bash
python3 scripts/local_asr.py transcribe "/absolute/path/to/job" \
  --output "/absolute/path/to/job/transcript.raw.json"
```

### 平台说明

- YouTube：优先获取公开字幕，访问可能受到平台登录或反自动化策略限制。
- 哔哩哔哩：使用公开接口获取元数据、字幕和音频，不把 yt-dlp 作为 B 站默认路径。
- 小宇宙：解析公开节目页面和音频地址，通常需要本地 ASR。
- 浏览器登录态：只有得到用户对当前来源的明确许可后才能使用。

### 导出文档

三种格式由同一份 Markdown 内容生成：

```bash
python3 scripts/document_export.py export document.md \
  --output-dir exports \
  --formats md,docx,pdf

python3 scripts/document_export.py validate exports
```

在 Codex 之外单独运行文档导出器时，可能需要安装：

```bash
pip install python-docx reportlab pypdf
```

### 本地自检

```bash
python3 scripts/self_test.py --output-dir /tmp/echoscript-self-test
```

自检覆盖本地媒体接入、ASR 模型检测、文稿分块及 Markdown、DOCX、PDF 导出。

---

## English

### What it does

EchoScript accepts:

- YouTube video URLs
- Bilibili video URLs
- Xiaoyuzhou podcast URLs
- Local audio, video, subtitle, or transcript files

The end-to-end workflow:

1. Acquires available platform subtitles or public audio.
2. Detects and uses a local ASR model when no transcript is available.
3. Uses the current Codex Agent for proofreading, English-to-Chinese translation, and content synthesis.
4. Produces separate quick summary, detailed summary, and topic-idea sections.
5. Exports Markdown, Word DOCX, and PDF documents.

Proofreading, translation, and summarization do not call an external LLM API. Notion and Feishu sync are intentionally deferred until the local workflow has been validated.

### Installation

Python 3, FFmpeg, FFprobe, curl, and yt-dlp are required. Clone the repository into the Codex Skills directory:

```bash
git clone https://github.com/zyipeng/echoscript-skill.git ~/.codex/skills/echoscript
```

Start a new Codex task after installation and invoke the Skill with `$echoscript`.

Check local dependencies with:

```bash
python3 ~/.codex/skills/echoscript/scripts/media_ingest.py doctor
python3 ~/.codex/skills/echoscript/scripts/local_asr.py doctor
```

### Example prompts

```text
Use $echoscript to process this YouTube URL. Proofread the transcript, translate English
into Chinese, create a quick summary, detailed summary, and topic ideas, then export
Markdown, Word, and PDF files.
```

For a local file:

```text
Use $echoscript to process /absolute/path/to/podcast.mp3 and export a Chinese transcript
in Markdown, Word, and PDF formats.
```

### Local ASR policy

EchoScript never downloads model weights silently during transcription:

1. It checks for existing FunASR and MLX models first.
2. A ready local model is reused immediately.
3. If model files exist but the runtime is missing, only runtime installation is suggested.
4. If no local ASR model exists, FunASR `iic/SenseVoiceSmall` is the preferred download.
5. Model downloads require explicit user approval.

Inspect the current state:

```bash
python3 scripts/local_asr.py doctor
```

After download approval, install the preferred FunASR backend:

```bash
python3 scripts/local_asr.py setup --backend funasr
```

Transcription automatically selects a ready local backend:

```bash
python3 scripts/local_asr.py transcribe "/absolute/path/to/job" \
  --output "/absolute/path/to/job/transcript.raw.json"
```

### Platform notes

- YouTube: public subtitles are preferred, but access may be limited by sign-in or anti-automation controls.
- Bilibili: public APIs are used for metadata, subtitles, and audio; yt-dlp is not the default Bilibili path.
- Xiaoyuzhou: public episode metadata and audio are parsed; local ASR is usually required.
- Browser sessions: signed-in browser state may be used only with explicit permission for the current source.

### Document export

All formats are generated from the same canonical Markdown document:

```bash
python3 scripts/document_export.py export document.md \
  --output-dir exports \
  --formats md,docx,pdf

python3 scripts/document_export.py validate exports
```

When running outside the bundled Codex environment, document export may require:

```bash
pip install python-docx reportlab pypdf
```

### Local self-test

```bash
python3 scripts/self_test.py --output-dir /tmp/echoscript-self-test
```

The self-test covers local media ingestion, ASR model detection, transcript chunking, and Markdown, DOCX, and PDF export.
