# EchoScript·声坊

> 🎙️ EchoScript是一个长音频转文稿处理 Skill，可以把 YouTube / 哔哩哔哩 / 小宇宙 / 本地音视频，一步转成校对文字稿、中文翻译、摘要、内容总结和选题推荐，并按需导出 Markdown / Word / PDF 格式文件。

[简体中文](#简体中文) · [English](#english)

中文快速入口：[30 秒上手](#30-秒上手) · [Claude Code 安装](#安装到-claude-code) · [Codex 安装](#安装到-codex) · [其他 Agent](#在其他-agent-中使用) · [环境变量](#环境变量与镜像加速) · [常见问题](#常见问题)

English quick links: [Quick start](#quick-start) · [Claude Code](#claude-code-installation) · [Codex](#codex-installation) · [Other agents](#other-agents-and-custom-locations) · [Environment](#environment-variables-and-mirrors) · [Troubleshooting](#troubleshooting)

---

## 简体中文

### 30 秒上手

#### 一句话操作指南：

复制这个项目链接，发送给你的agent，说帮我安装这个skill，并将这个播客链接转成文字稿，输出为md/word/pdf 格式文档。（初次使用时需要先安装本地ASR模型）

### 你可以用它做什么

支持的输入：

- YouTube 视频链接
- 哔哩哔哩视频链接
- 小宇宙播客链接
- 本地音频或视频
- 本地 SRT、VTT、纯文本等字幕或文字稿

支持的处理能力：

- 优先获取平台已有字幕
- 没有字幕时使用本地 FunASR 或 MLX Whisper 转写
- 校对错别字、断句、标点和明显的 ASR 错误
- 将英文文字稿翻译成自然中文
- 分别生成 `快速摘要`、`详细总结`、`灵感选题`
- 只导出你选择的 Markdown、Word DOCX、PDF 格式

翻译、校对和总结由当前 Agent 自身完成，EchoScript 不再额外接入另一套 LLM API。如果是超长音频，尽量使用高性价比模型，减少成本～～

### 工作流一览

```text
  输入源                本地脚本                        Agent 语言能力              产物
┌─────────┐   ingest   ┌──────────────┐   转写    ┌─────────────┐          ┌──────────┐
│ YouTube │──────────▶ │ media_ingest │─────────▶ │  local_asr  │          │ 校对文字稿 │
│ 哔哩哔哩 │           │  字幕/音频    │  (无字幕时) │ FunASR/MLX  │          │ 中文翻译   │
│ 小宇宙   │           └──────────────┘           └──────┬──────┘          │ 快速摘要   │
│ 本地音视频│                                            │ transcript.json  │ 详细总结   │
│ 字幕文件 │                                     ┌──────▼───────┐   Agent  │ 灵感选题   │
└─────────┘                                     │ chunk_transcript │──────▶│ document.md│
                                                └──────────────┘  校对/翻译 └─────┬────┘
                                                                    /总结         │ export
                                                                            ┌─────▼─────┐
                                                                            │ md/docx/pdf│
                                                                            └───────────┘
```

获取、转写、分块、导出是本地脚本；校对、翻译、总结依赖当前宿主 Agent 的语言能力。

### 先选一种安装方式

| 使用环境 | 推荐安装位置 | 调用方式 | 适用范围 |
| --- | --- | --- | --- |
| Claude Code 个人 Skill | `~/.claude/skills/echoscript` | `/echoscript` 或自然语言 | 所有 Claude Code 项目 |
| Claude Code 项目 Skill | `<项目>/.claude/skills/echoscript` | `/echoscript` 或自然语言 | 当前项目及其子目录 |
| Codex 个人 Skill | `~/.codex/skills/echoscript` | `$echoscript` 或自然语言 | 所有 Codex 任务 |
| 其他 Agent | 任意目录 | 让 Agent 读取该目录的 `SKILL.md` | 取决于该 Agent 的 Skill 机制 |

安装位置只是 Agent 的发现入口，EchoScript 脚本本身没有硬编码 Codex 路径。

### 系统要求

建议环境：

- macOS 或 Linux
- Windows 用户建议使用 WSL2；原生 Windows 尚未作为主要测试环境
- Python 3.10 或更高版本
- Git
- FFmpeg 和 FFprobe
- curl
- yt-dlp

macOS（Homebrew）：

```bash
brew install python ffmpeg curl yt-dlp git
```

Ubuntu / Debian / WSL：

```bash
sudo apt update
sudo apt install python3 python3-pip ffmpeg curl git
python3 -m pip install --upgrade yt-dlp
```

Word 和 PDF 导出依赖（`python-docx`、`reportlab`、`pypdf`）通常**无需手动安装**：导出脚本会自动装进 EchoScript 的隔离环境（见 [环境变量与镜像加速](#环境变量与镜像加速)），从而绕开系统 Python 的 PEP 668 限制。仅在你想手动预装时才需要：

```bash
python3 -m pip install python-docx reportlab pypdf
```

### 安装到 Claude Code

#### 个人安装：所有项目可用

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/zyipeng/echoscript-skill.git ~/.claude/skills/echoscript
```

然后在 Claude Code 中输入：

```text
/echoscript 处理这个小宇宙链接，生成摘要版，只导出 Markdown：<链接>
```

也可以不写命令名，直接描述需求。Claude Code 会根据 `SKILL.md` 的 description 自动判断是否调用 EchoScript：

```text
请处理这个英文 YouTube 视频，校对全文、翻译成中文并导出 Word：<链接>
```

#### 项目安装：只在当前仓库使用

如果项目已经使用 Git，并且希望团队成员获得同一版本，推荐在项目根目录添加 submodule：

```bash
mkdir -p .claude/skills
git submodule add https://github.com/zyipeng/echoscript-skill.git .claude/skills/echoscript
```

如果只是本机临时使用、不准备把 Skill 提交到当前项目，也可以把仓库直接 clone 到同一路径。

Claude Code 官方支持从 `.claude/skills/` 自动发现项目 Skill。若当前会话启动时还不存在顶层 Skill 目录，创建后没有立即出现 `/echoscript`，请重新启动一次 Claude Code。详见 [Claude Code Skills 官方文档](https://code.claude.com/docs/en/skills)。

### 安装到 Codex

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/zyipeng/echoscript-skill.git ~/.codex/skills/echoscript
```

建议安装后新建一个 Codex 任务，然后输入：

```text
用 $echoscript 处理这个哔哩哔哩链接，生成完整版，最后只导出 PDF：<链接>
```

也可以使用自然语言描述任务；`$echoscript` 是 Codex 的显式调用方式，不是 EchoScript 脚本本身的必需参数。

### 在其他 Agent 中使用

将仓库克隆到任意位置：

```bash
git clone https://github.com/zyipeng/echoscript-skill.git /path/to/echoscript
```

如果 Agent 支持 Agent Skills 标准，把整个目录放入该 Agent 的 Skills 目录。如果不支持自动发现，可以直接告诉它：

```text
请完整读取 /path/to/echoscript/SKILL.md，并严格按照其中工作流处理这个媒体：<链接或本地文件>。
需要完整版，英文翻译成中文，最后只导出 DOCX。
```

不要只复制 `SKILL.md`：`scripts/`、`references/` 和 `assets/` 都是工作流的一部分。

### 第一次运行

进入实际安装目录。下面用 `/path/to/echoscript` 表示该目录：

```bash
cd /path/to/echoscript
python3 scripts/media_ingest.py doctor
python3 scripts/local_asr.py doctor
```

第一条命令检查媒体获取依赖；第二条命令只检测本地 ASR 环境和模型，不会自动下载模型。

如果你只想快速确认整个本地工作流：

```bash
python3 scripts/self_test.py --output-dir /tmp/echoscript-self-test
```

自检覆盖本地媒体接入、ASR 模型检测、保留说话人边界的碎片合并与分块，以及 Markdown、DOCX、PDF 导出。

### 推荐提问方式

最好一次说清三件事：输入来源、内容范围、导出格式。

完整版示例：

```text
处理这个英文 YouTube 链接。校对完整文稿并翻译成中文，生成快速摘要、详细总结和灵感选题，只导出 Word：<链接>
```

摘要版示例：

```text
处理这个本地播客，只要快速摘要、详细总结和灵感选题，不需要完整文稿，只导出 Markdown：/absolute/path/to/podcast.mp3
```

如果没有说明内容范围或格式，Skill 会用一个简短问题确认：

- `摘要版`：快速摘要、详细总结、灵感选题，不附完整文稿。
- `完整版`：以上三部分，加完整校对文稿；英文源再附中文翻译。
- 导出格式：`md`、`docx`、`pdf`，可以多选，但不会默认同时生成三份。

### 本地 ASR 和模型下载规则

EchoScript 不会在转写时静默下载模型：

1. 已有可用字幕时跳过 ASR。
2. 没有字幕时先检测 FunASR 和 MLX 模型。
3. 已有模型但缺少运行环境时，只建议安装运行环境。
4. 没有本地模型时，优先提供 FunASR `iic/SenseVoiceSmall`；主模型约 1 GB。
5. 下载或安装前必须获得用户许可。
6. `whisper-tiny` 只用于冒烟测试，正式长音频必须先明确接受质量风险。

检测：

```bash
python3 scripts/local_asr.py doctor
```

获得下载许可后安装首选 FunASR：

```bash
python3 scripts/local_asr.py setup --backend funasr
```

`setup` 会把 FunASR 运行时**连同 `torch`、`torchaudio` 一起装入隔离环境**，并在装完后校验模块是否可用——避免出现「funasr 能导入但缺 torch，一转写就崩」的假就绪状态。安装过程会实时打印进度。

正常情况下应让 Agent 按 `recommended_action` 决定下一步，不需要手动猜测模型目录。

### 环境变量与镜像加速

默认从官方源下载依赖和模型在国内可能很慢。可在运行 `setup` 前导出以下变量加速：

| 变量 | 作用 |
| --- | --- |
| `ECHOSCRIPT_PIP_INDEX_URL` / `PIP_INDEX_URL` | pip 主镜像，如清华 `https://pypi.tuna.tsinghua.edu.cn/simple` |
| `ECHOSCRIPT_PIP_EXTRA_INDEX_URL` | pip 额外镜像 |
| `ECHOSCRIPT_HF_ENDPOINT` | HuggingFace 镜像端点（如 `https://hf-mirror.com`） |
| `ECHOSCRIPT_DOCUMENT_PYTHON` | 指定已装好 `python-docx/pypdf/reportlab` 的 Python，用于文档导出 |
| `ECHOSCRIPT_CACHE_DIR` | 覆盖默认缓存目录 `~/.cache/echoscript-skill` |

示例：

```bash
export ECHOSCRIPT_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export ECHOSCRIPT_HF_ENDPOINT=https://hf-mirror.com
python3 scripts/local_asr.py setup --backend funasr
```

**文档导出运行时自动发现顺序**：`ECHOSCRIPT_DOCUMENT_PYTHON` → EchoScript 自身的 `~/.cache/echoscript-skill/funasr-venv`（或 `asr-venv`）→ 旧版 Codex 运行时。若都不可用，脚本会自动把导出依赖装进已有的隔离环境，无需你手动处理 PEP 668 报错。

### Token 优化与质量边界

- 正常流程执行已有脚本，不读取 README 和 Python 源码；只有命令失败且诊断不足时才检查相关脚本。
- 不重复读取完整 `transcript.raw.json`；后续处理使用分块索引和对应 chunk。
- 同一说话人的短 ASR 片段默认合并成自然段，减少重复时间戳；`--no-merge` 可保留原始分段。
- 摘要版可以用带时间戳的 show notes 定位证据，但 show notes 不能替代文字稿。
- 完整版必须覆盖每一个分块，只通过“逐块读取一次 + 精简证据笔记”减少重复上下文。
- 完整文字稿只删除确定的 ASR 噪音或意外重复，不会因为观点已经出现在总结中而删除有意义的内容。
- 转写结果会标记 `timestamp_granularity`：若模型只给出整段级时间戳（`coarse`，无逐句时间轴），文档中的时间戳会被当作**章节近似导航**，并在「处理说明」中注明，不会伪装成精确逐句时间。

### 平台和隐私说明

- YouTube：优先获取公开字幕；部分视频可能受到登录或反自动化限制。
- 哔哩哔哩：优先使用公开接口获取元数据、字幕和音频，不把 yt-dlp 作为默认 B 站路径。
- 小宇宙：解析公开节目页面和音频地址，通常需要本地 ASR。
- 本地转写由本机 ASR 完成；EchoScript 不额外调用第三方 LLM API。校对、翻译和总结会进入当前宿主 Agent 的上下文，仍应遵循 Claude Code、Codex 或其他宿主的隐私与数据政策。
- 浏览器登录态：只有用户对当前来源明确授权后才能使用。

### 手动运行脚本

通常应让 Agent 按 `SKILL.md` 完成整套工作流。以下命令适合排查单个阶段：

```bash
# 获取媒体、字幕或音频
python3 scripts/media_ingest.py ingest "SOURCE" --output-dir "/absolute/output/job"

# 已确认本地 ASR 就绪后转写
python3 scripts/local_asr.py transcribe "/absolute/output/job" \
  --output "/absolute/output/job/transcript.raw.json"

# 合并短片段并分块
python3 scripts/chunk_transcript.py "/absolute/output/job/transcript.raw.json" \
  --output-dir "/absolute/output/job/chunks"

# 从 Agent 生成的 document.md 导出指定格式
python3 scripts/document_export.py export "/absolute/output/job/document.md" \
  --output-dir "/absolute/output/job/exports" \
  --formats "docx"

python3 scripts/document_export.py validate "/absolute/output/job/exports"
```

媒体获取、ASR、分块和导出是本地脚本；校对、翻译和总结需要 Agent 自身的语言能力，不能仅靠运行脚本完成。

### 常见问题

#### Claude Code 找不到 `/echoscript`

- 确认入口文件是 `~/.claude/skills/echoscript/SKILL.md`，或项目中的 `.claude/skills/echoscript/SKILL.md`。
- 不要多套一层目录，例如避免 `echoscript/echoscript/SKILL.md`。
- 如果 Skills 顶层目录是在当前会话启动后第一次创建，重启 Claude Code。
- 也可以直接用自然语言描述需求，让 Claude 根据 description 自动发现 Skill。

#### Codex 找不到 `$echoscript`

- 确认入口文件是 `~/.codex/skills/echoscript/SKILL.md`。
- 安装后新建一个 Codex 任务再试。
- 也可以把 `SKILL.md` 的绝对路径和任务一起交给 Agent。

#### 提示缺少 FFmpeg、FFprobe、curl 或 yt-dlp

先运行 `media_ingest.py doctor`，按输出安装缺失项。FFprobe 通常随 FFmpeg 一起安装。

#### 本地没有 ASR 模型

这是正常状态。`local_asr.py doctor` 会返回首选安装动作；只有获得许可后才下载 FunASR 模型。

#### MLX 报错 `No Metal device available`

MLX 需要 Apple Silicon 和可访问 Metal 的本机环境。受限沙箱中可在获得权限后重试；非 Apple Silicon 机器优先使用 FunASR。

#### Word 或 PDF 导出失败

导出脚本会优先自动把 `python-docx`、`reportlab`、`pypdf` 装入 EchoScript 的隔离环境。若仍失败，可先运行一次 `python3 scripts/local_asr.py setup --backend funasr` 创建隔离环境，或设置 `ECHOSCRIPT_DOCUMENT_PYTHON` 指向已装好这三个依赖的 Python，再重新运行导出和 validate 命令。国内下载慢可参考 [环境变量与镜像加速](#环境变量与镜像加速)。

### 更新

在安装目录执行：

```bash
git pull --ff-only
```

如果通过项目级安装与团队共享，建议使用 Git submodule 或其他固定版本依赖方式，避免不同成员得到不一致的工作流。

### 仓库结构

```text
echoscript/
├── SKILL.md                       # Agent 工作流入口
├── README.md                      # 面向用户的中英文说明
├── scripts/                       # 媒体、ASR、分块、导出和自检脚本
├── references/                    # 按需加载的平台与文本处理协议
├── assets/                        # 文档模板
└── agents/openai.yaml             # Codex UI 元数据，其他 Agent 可忽略
```

---

## English

EchoScript is a local-first Agent Skill for turning YouTube, Bilibili, Xiaoyuzhou, local media, subtitle files, or transcripts into proofread transcripts, Chinese translations, summaries, topic ideas, and selected Markdown, Word, or PDF deliverables.

**What makes it different:**

- 🔒 **Local-first & private** — ASR runs on your machine (FunASR / MLX Whisper); no separate third-party LLM API is called.
- 🧩 **Not tied to one agent** — Claude Code, Codex, and any agent that reads `SKILL.md` and runs local scripts can use it.
- 🎯 **Produce only what you ask** — pick summary-only vs full-transcript and pick export formats; it never defaults to three files.
- ⚙️ **Batteries-included runtime** — `setup` installs the full FunASR runtime (including `torch`); export dependencies are auto-provisioned into an isolated venv, sidestepping system-Python PEP 668 errors.

### Quick start

```bash
# 1. Install (Claude Code personal skill shown here)
git clone https://github.com/zyipeng/echoscript-skill.git ~/.claude/skills/echoscript

# 2. Check dependencies (ingest + local ASR; no model download)
cd ~/.claude/skills/echoscript
python3 scripts/media_ingest.py doctor
python3 scripts/local_asr.py doctor
```

Then state source + scope + format in one sentence:

```text
Process this Xiaoyuzhou link, summary-only, export Markdown only: <URL>
```

### Capabilities

- Prefer existing platform subtitles before ASR.
- Use local FunASR or MLX Whisper when transcription is required.
- Proofread timestamps, sentence boundaries, punctuation, and clear ASR mistakes.
- Translate proofread English transcripts into natural Chinese.
- Produce separate quick summary, detailed summary, and topic-idea sections.
- Export only the user-selected `md`, `docx`, or `pdf` formats.

Proofreading, translation, and summarization use the current agent's language ability; EchoScript does not call a separate LLM API. Notion and Feishu sync are intentionally deferred.

### Choose an installation scope

| Environment | Recommended location | Invocation | Scope |
| --- | --- | --- | --- |
| Claude Code personal skill | `~/.claude/skills/echoscript` | `/echoscript` or natural language | Every Claude Code project |
| Claude Code project skill | `<project>/.claude/skills/echoscript` | `/echoscript` or natural language | Current project |
| Codex personal skill | `~/.codex/skills/echoscript` | `$echoscript` or natural language | Every Codex task |
| Other agents | Any directory | Ask the agent to read `SKILL.md` | Depends on the host agent |

These locations are discovery conventions, not hard-coded script paths.

### Requirements

- macOS or Linux; Windows users are encouraged to use WSL2
- Python 3.10+
- Git
- FFmpeg and FFprobe
- curl
- yt-dlp

macOS with Homebrew:

```bash
brew install python ffmpeg curl yt-dlp git
```

Ubuntu, Debian, or WSL:

```bash
sudo apt update
sudo apt install python3 python3-pip ffmpeg curl git
python3 -m pip install --upgrade yt-dlp
```

Install document-export dependencies only if you want to preinstall them manually — the export script otherwise auto-provisions them into EchoScript's isolated venv (see [Environment variables and mirrors](#environment-variables-and-mirrors)):

```bash
python3 -m pip install python-docx reportlab pypdf
```

### Claude Code installation

Personal skill, available in every project:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/zyipeng/echoscript-skill.git ~/.claude/skills/echoscript
```

Project skill shared with a Git repository:

```bash
mkdir -p .claude/skills
git submodule add https://github.com/zyipeng/echoscript-skill.git .claude/skills/echoscript
```

For a local-only project installation that will not be committed, cloning directly into the same path is also acceptable.

Invoke it directly:

```text
/echoscript Process this English YouTube video, create a full transcript and Chinese translation, and export only DOCX: <URL>
```

Claude Code can also load the Skill automatically from a natural-language request that matches its description. If you create the top-level skills directory after the current session has started and the Skill does not appear, restart Claude Code once. See the [official Claude Code Skills documentation](https://code.claude.com/docs/en/skills) for discovery and scope details.

### Codex installation

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/zyipeng/echoscript-skill.git ~/.codex/skills/echoscript
```

Start a new Codex task after installation, then use:

```text
Use $echoscript to process this Bilibili URL, create the full transcript, and export only PDF: <URL>
```

`$echoscript` is Codex invocation syntax, not a requirement of the EchoScript scripts.

### Other agents and custom locations

Clone the complete repository anywhere:

```bash
git clone https://github.com/zyipeng/echoscript-skill.git /path/to/echoscript
```

If the host agent supports the Agent Skills standard, place the directory in its Skills location. Otherwise prompt it explicitly:

```text
Read /path/to/echoscript/SKILL.md completely and follow it to process this media.
Create the full transcript, translate English into Chinese, and export only DOCX: <URL or local file>
```

Keep `scripts/`, `references/`, and `assets/` with `SKILL.md`; they are required parts of the workflow.

### First-run check

From the actual installation directory:

```bash
python3 scripts/media_ingest.py doctor
python3 scripts/local_asr.py doctor
```

The ASR doctor detects runtimes and cached models but does not download model weights.

Run the deterministic local self-test with:

```bash
python3 scripts/self_test.py --output-dir /tmp/echoscript-self-test
```

### Request content and format explicitly

Full-transcript example:

```text
Process this English YouTube URL. Proofread the complete transcript, translate it into Chinese, create all three summary sections, and export only Word: <URL>
```

Summary-only example:

```text
Process this local podcast. Create only the quick summary, detailed summary, and topic ideas. Do not include the full transcript. Export Markdown: /absolute/path/to/podcast.mp3
```

When unspecified, the Skill asks once for the missing choices:

- `summary-only`: quick summary, detailed summary, and topic ideas.
- `full-transcript`: those sections plus the complete proofread transcript and, for English sources, a Chinese translation.
- Formats: `md`, `docx`, `pdf`, or an explicit combination. It never defaults to three duplicate files.

### Local ASR policy

EchoScript never downloads model weights silently:

1. Existing subtitles skip ASR.
2. Local FunASR and MLX models are detected first.
3. Existing model files are reused; missing runtimes are handled separately.
4. When no model exists, FunASR `iic/SenseVoiceSmall` is offered first; its main model is about 1 GB.
5. Setup or model download requires explicit approval.
6. `whisper-tiny` is smoke-test-only and requires explicit quality-risk acceptance for real transcripts.

`setup --backend funasr` installs the FunASR runtime together with `torch`/`torchaudio` into an isolated venv and verifies the modules afterwards, so a torch-less environment is no longer falsely reported as ready. Install progress is streamed to stdout.

### Environment variables and mirrors

Downloading from default indexes can be slow. Export these before `setup` to speed things up:

| Variable | Purpose |
| --- | --- |
| `ECHOSCRIPT_PIP_INDEX_URL` / `PIP_INDEX_URL` | Primary pip mirror |
| `ECHOSCRIPT_PIP_EXTRA_INDEX_URL` | Extra pip mirror |
| `ECHOSCRIPT_HF_ENDPOINT` | HuggingFace mirror endpoint (e.g. `https://hf-mirror.com`) |
| `ECHOSCRIPT_DOCUMENT_PYTHON` | Python that already has `python-docx/pypdf/reportlab`, used for export |
| `ECHOSCRIPT_CACHE_DIR` | Override the default cache dir `~/.cache/echoscript-skill` |

The exporter discovers a runtime in this order: `ECHOSCRIPT_DOCUMENT_PYTHON` → EchoScript's own `~/.cache/echoscript-skill/funasr-venv` (or `asr-venv`) → legacy Codex runtimes. If none are ready it provisions the packages into an existing venv, avoiding PEP 668 failures on system Python.

### Token efficiency without silent quality loss

- Normal runs execute documented scripts without reading their source code or this README.
- The raw transcript JSON is not reread after compact chunks are produced.
- Short same-speaker ASR fragments are merged into natural paragraphs by default.
- Summary-only mode may use timestamped show notes for navigation, but transcript evidence remains authoritative.
- Full-transcript mode covers every indexed chunk once and synthesizes from compact evidence notes.
- Meaningful transcript content is never removed merely because the summary already mentions it.
- Transcripts carry a `timestamp_granularity` flag; when it is `coarse` (whole-audio segment, no per-sentence timeline), in-document timestamps are treated as approximate chapter navigation and labeled as such in the processing notes.

### Platform, privacy, and current scope

- YouTube: public subtitles are preferred; sign-in and anti-automation restrictions may still apply.
- Bilibili: public APIs are preferred for metadata, subtitles, and audio; yt-dlp is not the default Bilibili path.
- Xiaoyuzhou: public episode metadata and audio are parsed; local ASR is usually required.
- ASR runs locally, and EchoScript does not call a separate third-party LLM API. Proofreading, translation, and summarization still enter the current host agent's context and remain subject to that host's privacy and data policies.
- Signed-in browser state requires explicit permission for the current source.
- Notion and Feishu upload are not included in this phase.

### Troubleshooting

**Claude Code does not show `/echoscript`:** verify `~/.claude/skills/echoscript/SKILL.md` or `<project>/.claude/skills/echoscript/SKILL.md`, avoid an extra nested directory, and restart Claude Code if the top-level Skills directory was created after the session started.

**Codex does not discover `$echoscript`:** verify `~/.codex/skills/echoscript/SKILL.md` and start a new task after installation.

**A media dependency is missing:** run `python3 scripts/media_ingest.py doctor`. FFprobe normally ships with FFmpeg.

**No local ASR model exists:** run `python3 scripts/local_asr.py doctor` and follow `recommended_action`; model setup still requires approval.

**MLX reports `No Metal device available`:** MLX requires Apple Silicon and Metal access. Retry outside a restricted sandbox when authorized, or use FunASR on other hardware.

**DOCX or PDF export fails:** the exporter first auto-provisions `python-docx`, `reportlab`, and `pypdf` into EchoScript's isolated venv. If it still fails, run `python3 scripts/local_asr.py setup --backend funasr` once to create the venv, or set `ECHOSCRIPT_DOCUMENT_PYTHON` to a Python that already has the three packages, then rerun export and validation. For slow downloads see [Environment variables and mirrors](#environment-variables-and-mirrors).

### Updating

From the installed repository:

```bash
git pull --ff-only
```

### Repository layout

```text
echoscript/
├── SKILL.md                       # Agent workflow entrypoint
├── README.md                      # Bilingual user documentation
├── scripts/                       # Ingest, ASR, chunking, export, and tests
├── references/                    # On-demand platform and processing rules
├── assets/                        # Document template
└── agents/openai.yaml             # Codex UI metadata; other agents may ignore it
```
