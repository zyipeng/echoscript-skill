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
5. 只导出用户选择的 Markdown、Word DOCX 或 PDF 格式。

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

### 其他 Agent 或任意路径使用

`~/.codex/skills/echoscript` 是 Codex 的推荐安装位置，不是脚本的硬编码依赖。也可以把仓库 clone 到任意目录，让支持 `SKILL.md` 工作流的 Agent 读取该文件，并使用脚本的绝对路径执行命令。不同 Agent 是否支持 `$echoscript` 自动触发，取决于各自的 Skill 发现机制。

### 使用示例

在 Codex 中输入：

```text
用 $echoscript 处理这个 YouTube 链接。校对文稿，如果是英文就翻译成中文，
生成快速摘要、详细总结和灵感选题，最后只导出 Word。
```

也可以提供本地文件：

```text
用 $echoscript 处理 /absolute/path/to/podcast.mp3，并输出中文文稿和 PDF。
```

如果没有指定内容范围或格式，Skill 会用一个简短问题同时确认：

- `摘要版`：快速摘要、详细总结和灵感选题，不附完整文稿。
- `完整版`：以上三部分，加完整校对文稿；英文源再附中文翻译。

Skill 只生成用户选择的 Markdown、Word、PDF 格式，不会默认生成三份重复内容。

### Token 优化与质量边界

- 正常运行只执行文档中的命令，不读取 README 或 Python 源码；只有命令失败且诊断不足时才检查相关脚本。
- 分块脚本默认合并同一说话人、间隔不超过 2 秒且总跨度不超过 30 秒的碎片，减少重复时间戳并改善上下文。用 `--no-merge` 可保留原始分段。
- 摘要版可用带时间戳的 show notes 定位证据，但 show notes 不能替代文字稿；提纲稀疏时仍需覆盖全部分块。
- 完整版必须处理每一个分块。最终汇总使用逐块保存的精简证据笔记，避免再次读取整份原始文稿。
- 完整文字稿只删除确定的 ASR 噪音或意外重复，不会因为观点已出现在总结中就删掉有意义的原话。

### 本地 ASR 规则

EchoScript 不会在转写时静默下载模型：

1. 先检查本机已有的 FunASR 和 MLX 模型。
2. 如果已有可用模型，直接复用。
3. 如果只有模型、没有运行环境，只提示安装运行环境，不重复下载模型。
4. 如果没有任何本地 ASR 模型，优先提供 FunASR `iic/SenseVoiceSmall` 下载选项。
5. 下载模型前必须先获得用户许可。

如果本机只有 `whisper-tiny`，检测结果会将它标记为 `smoke-test-only`。它不会被静默用于正式长音频；用户必须明确接受质量风险并传入 `--allow-low-quality-model`，否则应升级到 FunASR SenseVoiceSmall 或已缓存的 whisper-small。

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

先确定需要的格式，再传给 `--formats`。该参数是必填项，可以是 `md`、`docx`、`pdf` 或逗号分隔的组合；下面只生成 Word：

```bash
python3 scripts/document_export.py export document.md \
  --output-dir exports \
  --formats docx

python3 scripts/document_export.py validate exports
```

`document.md` 是内部统一内容源。只有用户选择 Markdown 时，才把 Markdown 作为最终交付文档复制到导出目录。导出器也会拒绝仍含模板占位符的内容。

在 Codex 之外单独运行文档导出器时，可能需要安装：

```bash
pip install python-docx reportlab pypdf
```

### 本地自检

```bash
python3 scripts/self_test.py --output-dir /tmp/echoscript-self-test
```

自检覆盖本地媒体接入、ASR 模型检测、保留说话人边界的碎片合并与分块，以及 Markdown、DOCX、PDF 导出。

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
5. Exports only the Markdown, Word DOCX, or PDF formats selected by the user.

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

### Other agents and custom locations

`~/.codex/skills/echoscript` is the recommended Codex location, not a hard-coded script dependency. The repository can be cloned anywhere. An agent that supports `SKILL.md` workflows can read the file and run scripts by absolute path. Whether `$echoscript` is discovered automatically depends on that agent's own Skill mechanism.

### Example prompts

```text
Use $echoscript to process this YouTube URL. Proofread the transcript, translate English
into Chinese, create a quick summary, detailed summary, and topic ideas, then export
only a Word document.
```

For a local file:

```text
Use $echoscript to process /absolute/path/to/podcast.mp3 and export a Chinese transcript
as PDF.
```

If the content scope or format is missing, the Skill resolves both in one concise question:

- `summary-only`: quick summary, detailed summary, and topic ideas without a full transcript.
- `full-transcript`: those three sections plus the complete proofread transcript and, for English sources, a Chinese translation.

Only the selected Markdown, Word, or PDF deliverables are generated; the Skill never defaults to three duplicate files.

### Token efficiency and quality boundary

- A normal run executes documented commands without reading the README or Python source. Script inspection is reserved for an unexplained command failure.
- Chunking merges same-speaker fragments by default when their gap is at most 2 seconds and total span is at most 30 seconds. Pass `--no-merge` to preserve every source boundary.
- Summary-only mode may use timestamped show notes to route evidence lookup, but show notes never replace transcript evidence; sparse outlines trigger full chunk coverage.
- Full-transcript mode processes every indexed chunk once, saves compact evidence notes, and synthesizes from those notes instead of rereading all raw chunks.
- A full transcript removes only clear ASR noise or accidental duplicates. Meaningful speech is not deleted merely because a summary already covers it.

### Local ASR policy

EchoScript never downloads model weights silently during transcription:

1. It checks for existing FunASR and MLX models first.
2. A ready local model is reused immediately.
3. If model files exist but the runtime is missing, only runtime installation is suggested.
4. If no local ASR model exists, FunASR `iic/SenseVoiceSmall` is the preferred download.
5. Model downloads require explicit user approval.

If only `whisper-tiny` is available, the detector marks it as `smoke-test-only`. It is not silently used for production-length audio: the user must explicitly accept the quality risk and pass `--allow-low-quality-model`, or upgrade to FunASR SenseVoiceSmall or a cached whisper-small model.

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

Choose the deliverable first and pass it to the required `--formats` argument. Accepted values are `md`, `docx`, `pdf`, or a comma-separated combination. This example generates Word only:

```bash
python3 scripts/document_export.py export document.md \
  --output-dir exports \
  --formats docx

python3 scripts/document_export.py validate exports
```

`document.md` remains the internal canonical source. Markdown is copied into the export directory only when the user selects it as a deliverable. The exporter also rejects unresolved template placeholders.

When running outside the bundled Codex environment, document export may require:

```bash
pip install python-docx reportlab pypdf
```

### Local self-test

```bash
python3 scripts/self_test.py --output-dir /tmp/echoscript-self-test
```

The self-test covers local media ingestion, ASR model detection, speaker-safe transcript merging and chunking, and Markdown, DOCX, and PDF export.
