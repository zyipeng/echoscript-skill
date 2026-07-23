#!/usr/bin/env python3
"""Detect and run local ASR without silently downloading model weights."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any


DEFAULT_CACHE_DIR = Path.home() / ".cache" / "echoscript-skill"
FUNASR_MODEL = "iic/SenseVoiceSmall"
FUNASR_VAD_MODEL = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
MLX_DEFAULT_MODEL = "mlx-community/whisper-small-mlx"
MLX_TINY_MODEL = "mlx-community/whisper-tiny-mlx"

# Runtime Python modules required before FunASR can actually transcribe.
# funasr imports torch at call time, so torch must be present or the worker
# crashes with "缺少 torch" even though funasr itself is installed.
FUNASR_RUNTIME_MODULES = ("funasr", "modelscope", "torch", "torchaudio")
FUNASR_PIP_PACKAGES = ("funasr", "modelscope", "torch", "torchaudio")


class AsrError(RuntimeError):
    pass


def pip_mirror_env() -> dict[str, str]:
    """Return environment overrides enabling optional pip / model mirrors.

    Users in mainland China can export ECHOSCRIPT_PIP_INDEX_URL (or the
    standard PIP_INDEX_URL) plus ECHOSCRIPT_HF_ENDPOINT / MODELSCOPE mirrors to
    dramatically speed up otherwise ~40kB/s default-index downloads.
    """
    environment = os.environ.copy()
    pip_index = os.environ.get("ECHOSCRIPT_PIP_INDEX_URL") or os.environ.get("PIP_INDEX_URL")
    if pip_index:
        environment["PIP_INDEX_URL"] = pip_index
    pip_extra = os.environ.get("ECHOSCRIPT_PIP_EXTRA_INDEX_URL")
    if pip_extra:
        environment["PIP_EXTRA_INDEX_URL"] = pip_extra
    hf_endpoint = os.environ.get("ECHOSCRIPT_HF_ENDPOINT")
    if hf_endpoint:
        environment["HF_ENDPOINT"] = hf_endpoint
    return environment


def run_streaming(command: list[str], *, env: dict[str, str] | None = None, label: str | None = None) -> None:
    """Run a subprocess while streaming its output so slow installs show progress."""
    if label:
        print(f"[echoscript] {label}", flush=True)
    print(f"[echoscript] $ {' '.join(command)}", flush=True)
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        raise AsrError(f"命令执行失败（退出码 {result.returncode}）：{' '.join(command)}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def python_has_module(executable: Path, module: str) -> bool:
    if not executable.is_file():
        return False
    result = subprocess.run(
        [
            str(executable),
            "-c",
            "import importlib.util, sys; "
            f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def environment_python(cache_dir: Path, backend: str) -> Path:
    name = "funasr-venv" if backend == "funasr" else "asr-venv"
    return cache_dir / name / "bin" / "python"


def python_has_all_modules(executable: Path, modules: tuple[str, ...]) -> bool:
    return all(python_has_module(executable, module) for module in modules)


def resolve_asr_python(cache_dir: Path, backend: str) -> Path | None:
    # A FunASR runtime is only usable when torch/torchaudio are also present;
    # checking just "funasr" produced false "ready" states that crashed at
    # transcribe time. Require the full runtime module set for funasr.
    modules = FUNASR_RUNTIME_MODULES if backend == "funasr" else ("mlx_whisper",)
    override_name = "ECHOSCRIPT_FUNASR_PYTHON" if backend == "funasr" else "ECHOSCRIPT_ASR_PYTHON"
    override = os.environ.get(override_name)
    candidates = [
        Path(override).expanduser() if override else None,
        environment_python(cache_dir, backend),
        Path(sys.executable),
    ]
    return next(
        (candidate for candidate in candidates if candidate and python_has_all_modules(candidate, modules)),
        None,
    )


def model_index_path(cache_dir: Path) -> Path:
    return cache_dir / "funasr-models.json"


def read_model_index(cache_dir: Path) -> dict[str, str]:
    path = model_index_path(cache_dir)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, dict):
        return {}
    return {str(key): str(value) for key, value in models.items()}


def write_model_index(cache_dir: Path, models: dict[str, Path]) -> None:
    write_json(model_index_path(cache_dir), {
        "schema_version": 1,
        "updated_at": utc_now(),
        "models": {key: str(value.resolve()) for key, value in models.items()},
    })


def valid_funasr_model_dir(path: Path) -> bool:
    if not path.is_dir() or not (path / "config.yaml").is_file():
        return False
    weight_names = (
        "model.pt",
        "model.pb",
        "model.bin",
        "pytorch_model.bin",
        "model.safetensors",
        "model.onnx",
    )
    return any((path / name).is_file() for name in weight_names)


def modelscope_candidates(model_id: str, cache_dir: Path) -> list[Path]:
    owner, name = model_id.split("/", 1)
    roots: list[Path] = [cache_dir / "funasr-models"]
    configured = os.environ.get("MODELSCOPE_CACHE")
    if configured:
        roots.append(Path(configured).expanduser())
    roots.extend([
        Path.home() / ".cache" / "modelscope" / "hub",
        Path.home() / ".cache" / "modelscope",
    ])
    candidates: list[Path] = []
    for root in roots:
        candidates.extend([
            root / owner / name,
            root / "models" / owner / name,
            root / "hub" / owner / name,
            root / "hub" / "models" / owner / name,
        ])
    return candidates


def find_funasr_model(model_id: str, cache_dir: Path, override_name: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if override_name and os.environ.get(override_name):
        candidates.append(Path(os.environ[override_name]).expanduser())
    indexed = read_model_index(cache_dir).get(model_id)
    if indexed:
        candidates.append(Path(indexed).expanduser())
    candidates.extend(modelscope_candidates(model_id, cache_dir))
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if valid_funasr_model_dir(resolved):
            return resolved
    return None


def mlx_model_is_cached(model: str) -> bool:
    local = Path(model).expanduser()
    if local.exists():
        return True
    if "/" not in model:
        return False
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")).expanduser()
    snapshots = hf_home / "hub" / f"models--{model.replace('/', '--')}" / "snapshots"
    return (
        any(path.exists() for path in snapshots.glob("*/config.json"))
        and any(path.exists() for path in snapshots.glob("*/weights.npz"))
    )


def model_quality(backend: str | None, model: str | None) -> dict[str, Any]:
    if backend == "funasr":
        return {"tier": "preferred", "requires_confirmation": False, "warning": None}
    if model == MLX_TINY_MODEL:
        return {
            "tier": "smoke-test-only",
            "requires_confirmation": True,
            "warning": (
                "当前仅检测到 whisper-tiny。它适合快速冒烟测试，但不适合直接生成长中文音频的正式文稿，"
                "容易出现同音字、专有名词和语义断裂问题。建议下载 FunASR SenseVoiceSmall 或缓存 whisper-small；"
                "只有用户明确接受质量风险时才使用 tiny。"
            ),
        }
    if backend == "mlx-whisper" and model:
        return {"tier": "standard", "requires_confirmation": False, "warning": None}
    return {"tier": "unavailable", "requires_confirmation": False, "warning": None}


def local_asr_state(cache_dir: Path) -> dict[str, Any]:
    funasr_python = resolve_asr_python(cache_dir, "funasr")
    funasr_model = find_funasr_model(FUNASR_MODEL, cache_dir, "ECHOSCRIPT_FUNASR_MODEL")
    funasr_vad = find_funasr_model(FUNASR_VAD_MODEL, cache_dir, "ECHOSCRIPT_FUNASR_VAD_MODEL")
    funasr_ready = bool(funasr_python and funasr_model and funasr_vad)

    mlx_python = resolve_asr_python(cache_dir, "mlx")
    mlx_model = next(
        (model for model in (MLX_DEFAULT_MODEL, MLX_TINY_MODEL) if mlx_model_is_cached(model)),
        None,
    )
    apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"
    mlx_ready = bool(mlx_python and mlx_model and apple_silicon)

    selected_backend = "funasr" if funasr_ready else "mlx-whisper" if mlx_ready else None
    selected_model = FUNASR_MODEL if funasr_ready else mlx_model if mlx_ready else None
    local_model_available = bool(funasr_model or mlx_model)
    quality = model_quality(selected_backend, selected_model)

    if selected_backend and quality["requires_confirmation"]:
        recommended_action = "confirm_low_quality_or_offer_upgrade"
        setup_command = f"python3 {Path(__file__).resolve()} setup --backend funasr"
    elif selected_backend:
        recommended_action = "none"
        setup_command = None
    elif funasr_model and funasr_vad:
        recommended_action = "install_funasr_runtime"
        setup_command = f"python3 {Path(__file__).resolve()} setup --backend funasr --skip-model-download"
    elif funasr_model:
        recommended_action = "offer_missing_funasr_vad_download"
        setup_command = f"python3 {Path(__file__).resolve()} setup --backend funasr"
    elif mlx_model:
        recommended_action = "install_mlx_runtime"
        setup_command = (
            f"python3 {Path(__file__).resolve()} setup --backend mlx "
            f"--model {mlx_model} --skip-model-download"
        )
    else:
        recommended_action = "offer_funasr_download"
        setup_command = f"python3 {Path(__file__).resolve()} setup --backend funasr"

    return {
        "ready": bool(selected_backend),
        "selected_backend": selected_backend,
        "selected_model": selected_model,
        "preferred_model": FUNASR_MODEL,
        "quality_tier": quality["tier"],
        "quality_warning": quality["warning"],
        "requires_quality_confirmation": quality["requires_confirmation"],
        "local_model_available": local_model_available,
        "recommended_action": recommended_action,
        "setup_command": setup_command,
        "funasr": {
            "ready": funasr_ready,
            "python": str(funasr_python) if funasr_python else None,
            "model_id": FUNASR_MODEL,
            "model_path": str(funasr_model) if funasr_model else None,
            "model_cached": bool(funasr_model),
            "vad_model_id": FUNASR_VAD_MODEL,
            "vad_model_path": str(funasr_vad) if funasr_vad else None,
            "vad_model_cached": bool(funasr_vad),
        },
        "mlx_whisper": {
            "ready": mlx_ready,
            "apple_silicon": apple_silicon,
            "python": str(mlx_python) if mlx_python else None,
            "preferred_model": MLX_DEFAULT_MODEL,
            "cached_model": mlx_model,
            "quality_tier": model_quality("mlx-whisper", mlx_model)["tier"],
        },
        "preferred_download": {
            "backend": "funasr",
            "model_id": FUNASR_MODEL,
            "companion_vad_model_id": FUNASR_VAD_MODEL,
            "approximate_main_model_size": "about 1 GB",
            "command": f"python3 {Path(__file__).resolve()} setup --backend funasr",
        },
    }


def doctor(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    payload = local_asr_state(cache_dir)
    payload["cache_dir"] = str(cache_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def create_venv(cache_dir: Path, backend: str) -> tuple[Path, Path]:
    venv_dir = cache_dir / ("funasr-venv" if backend == "funasr" else "asr-venv")
    python = environment_python(cache_dir, backend)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    return python, venv_dir / "bin" / "pip"


def parse_last_json_line(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AsrError("模型下载命令没有返回可解析的结果")


def setup_funasr(args: argparse.Namespace, cache_dir: Path) -> dict[str, Any]:
    python, pip = create_venv(cache_dir, "funasr")
    # torch/torchaudio are required at transcribe time; install them together
    # with funasr so the runtime is genuinely usable, not just importable.
    runtime_present = python_has_all_modules(python, FUNASR_RUNTIME_MODULES)
    installed_packages: list[str] = []
    if not runtime_present or args.upgrade:
        command = [str(pip), "install"]
        if args.upgrade:
            command.append("--upgrade")
        command.extend(FUNASR_PIP_PACKAGES)
        run_streaming(
            command,
            env=pip_mirror_env(),
            label=f"安装 FunASR 运行时依赖：{', '.join(FUNASR_PIP_PACKAGES)}",
        )
        installed_packages = list(FUNASR_PIP_PACKAGES)
        # Fail fast with an actionable message if the runtime is still broken.
        missing_modules = [m for m in FUNASR_RUNTIME_MODULES if not python_has_module(python, m)]
        if missing_modules:
            raise AsrError(
                "FunASR 运行时安装后仍缺少模块：" + ", ".join(missing_modules)
                + "。可设置 ECHOSCRIPT_PIP_INDEX_URL 使用国内镜像后重试。"
            )

    main_model = find_funasr_model(FUNASR_MODEL, cache_dir, "ECHOSCRIPT_FUNASR_MODEL")
    vad_model = find_funasr_model(FUNASR_VAD_MODEL, cache_dir, "ECHOSCRIPT_FUNASR_VAD_MODEL")
    downloaded: list[str] = []
    models = {
        key: value
        for key, value in ((FUNASR_MODEL, main_model), (FUNASR_VAD_MODEL, vad_model))
        if value
    }
    missing = [
        model_id
        for model_id, path in ((FUNASR_MODEL, main_model), (FUNASR_VAD_MODEL, vad_model))
        if not path
    ]
    if missing and not args.skip_model_download:
        command = [
            str(python), str(Path(__file__).resolve()), "_download_funasr",
            "--cache-root", str(cache_dir / "funasr-models"),
        ]
        for model_id in missing:
            command.extend(["--model-id", model_id])
        result = subprocess.run(command, check=True, text=True, capture_output=True, env=pip_mirror_env())
        payload = parse_last_json_line(result.stdout)
        for model_id, value in (payload.get("models") or {}).items():
            path = Path(str(value)).expanduser().resolve()
            if not valid_funasr_model_dir(path):
                raise AsrError(f"FunASR 模型下载不完整：{model_id}")
            models[str(model_id)] = path
            downloaded.append(str(model_id))
    if models:
        write_model_index(cache_dir, models)
    return {
        "backend": "funasr",
        "python": str(python),
        "installed_packages": installed_packages,
        "downloaded": downloaded,
        "model_download_skipped": bool(args.skip_model_download),
        "state": local_asr_state(cache_dir),
    }


def setup_mlx(args: argparse.Namespace, cache_dir: Path) -> dict[str, Any]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise AsrError("MLX Whisper 只支持 Apple Silicon Mac；请使用默认 FunASR 后端")
    python, pip = create_venv(cache_dir, "mlx")
    if not python_has_module(python, "mlx_whisper") or args.upgrade:
        command = [str(pip), "install"]
        if args.upgrade:
            command.append("--upgrade")
        command.append("mlx-whisper")
        run_streaming(command, env=pip_mirror_env(), label="安装 MLX Whisper 运行时")
    model = args.model or MLX_DEFAULT_MODEL
    downloaded: list[str] = []
    if not mlx_model_is_cached(model) and not args.skip_model_download:
        code = "from huggingface_hub import snapshot_download; snapshot_download(repo_id=" + repr(model) + ")"
        run_streaming([str(python), "-c", code], env=pip_mirror_env(), label=f"下载 MLX 模型 {model}")
        downloaded.append(model)
    return {
        "backend": "mlx-whisper",
        "python": str(python),
        "downloaded": downloaded,
        "model_download_skipped": bool(args.skip_model_download),
        "state": local_asr_state(cache_dir),
    }


def setup(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    result = setup_funasr(args, cache_dir) if args.backend == "funasr" else setup_mlx(args, cache_dir)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


def download_funasr_worker(args: argparse.Namespace) -> None:
    try:
        from modelscope import snapshot_download
    except ImportError as error:
        raise AsrError("FunASR 下载环境缺少 modelscope") from error
    root = Path(args.cache_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    models: dict[str, str] = {}
    for model_id in args.model_id:
        path = snapshot_download(model_id=model_id, cache_dir=str(root))
        models[model_id] = str(Path(path).resolve())
    print(json.dumps({"models": models}, ensure_ascii=False))


def resolve_audio(value: str) -> tuple[Path, Path | None]:
    path = Path(value).expanduser().resolve()
    source_manifest: Path | None = None
    if path.is_dir():
        source_manifest = path / "source.json"
        if not source_manifest.is_file():
            raise AsrError(f"目录缺少 source.json：{path}")
        payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        audio = payload.get("audio_path")
        if not audio:
            raise AsrError("source.json 没有 audio_path；来源可能只有字幕或使用了 --metadata-only")
        path = Path(str(audio)).expanduser().resolve()
    elif path.name == "source.json":
        source_manifest = path
        payload = json.loads(path.read_text(encoding="utf-8"))
        audio = payload.get("audio_path")
        if not audio:
            raise AsrError("source.json 没有 audio_path")
        path = Path(str(audio)).expanduser().resolve()
    if not path.is_file():
        raise AsrError(f"音频文件不存在：{path}")
    return path, source_manifest


def setup_message(state: dict[str, Any]) -> str:
    action = state["recommended_action"]
    command = state.get("setup_command")
    if action == "confirm_low_quality_or_offer_upgrade":
        return (
            f"{state['quality_warning']} 获得模型下载许可后可运行：{command}。"
            "若用户明确接受测试级质量，可在转写命令中加入 --allow-low-quality-model。"
        )
    if action == "offer_funasr_download":
        return (
            "本地未检测到可用 ASR 模型。先向用户说明将下载 FunASR SenseVoiceSmall "
            f"（主模型约 1 GB）并获得许可，再运行：{command}"
        )
    if action == "offer_missing_funasr_vad_download":
        return f"已找到 FunASR 主模型，但缺少本地 VAD 组件。获得下载许可后运行：{command}"
    if command:
        return f"检测到本地模型，但运行环境尚未安装。获得安装许可后运行：{command}"
    return "本地 ASR 尚未就绪"


def select_backend(args: argparse.Namespace, cache_dir: Path) -> tuple[str, str, Path]:
    state = local_asr_state(cache_dir)
    requested = args.backend
    if requested == "auto" and args.model:
        requested = "mlx" if args.model.startswith("mlx-community/") else "funasr"
    if requested == "auto":
        if state["funasr"]["ready"]:
            requested = "funasr"
        elif state["mlx_whisper"]["ready"]:
            requested = "mlx"
        else:
            raise AsrError(setup_message(state))
    if requested == "funasr":
        model_id = args.model or FUNASR_MODEL
        model_path = find_funasr_model(model_id, cache_dir, "ECHOSCRIPT_FUNASR_MODEL")
        vad_path = find_funasr_model(FUNASR_VAD_MODEL, cache_dir, "ECHOSCRIPT_FUNASR_VAD_MODEL")
        python = resolve_asr_python(cache_dir, "funasr")
        if not (model_path and vad_path and python):
            raise AsrError(setup_message(state))
        return "funasr", model_id, python
    model = args.model or state["mlx_whisper"]["cached_model"] or MLX_DEFAULT_MODEL
    python = resolve_asr_python(cache_dir, "mlx")
    if not python:
        raise AsrError(setup_message(state))
    if not mlx_model_is_cached(model):
        raise AsrError(
            f"本地尚未缓存 {model}。获得许可后运行：python3 {Path(__file__).resolve()} "
            f"setup --backend mlx --model {model}"
        )
    if model == MLX_TINY_MODEL and not args.allow_low_quality_model:
        raise AsrError(setup_message({
            **state,
            "recommended_action": "confirm_low_quality_or_offer_upgrade",
            "quality_warning": model_quality("mlx-whisper", model)["warning"],
            "setup_command": f"python3 {Path(__file__).resolve()} setup --backend funasr",
        }))
    return "mlx", model, python


def transcribe(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    audio, source_manifest = resolve_audio(args.input)
    backend, model, python = select_backend(args, cache_dir)
    effective_language = args.language
    if effective_language == "auto" and source_manifest:
        source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        manifest_language = str(source_payload.get("language") or "unknown").lower()
        if manifest_language in {"zh", "en", "yue", "ja", "ko"}:
            effective_language = manifest_language
    output = Path(args.output).expanduser().resolve()
    worker = [str(python), str(Path(__file__).resolve())]
    if backend == "funasr":
        model_path = find_funasr_model(model, cache_dir, "ECHOSCRIPT_FUNASR_MODEL")
        vad_path = find_funasr_model(FUNASR_VAD_MODEL, cache_dir, "ECHOSCRIPT_FUNASR_VAD_MODEL")
        worker.extend([
            "_funasr_worker", str(audio), str(output),
            "--model-id", model,
            "--model-path", str(model_path),
            "--vad-path", str(vad_path),
        ])
        transcript_origin = "local-funasr-sensevoice"
    else:
        worker.extend(["_mlx_worker", str(audio), str(output), "--model", model])
        transcript_origin = "local-mlx-whisper"
    if effective_language and effective_language != "auto":
        worker.extend(["--language", effective_language])
    worker_environment = os.environ.copy()
    worker_environment.update({
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "TQDM_DISABLE": "1",
    })
    result = subprocess.run(worker, env=worker_environment)
    if result.returncode != 0:
        raise AsrError(f"本地 {backend} 转写失败")
    granularity = "unknown"
    try:
        produced = json.loads(output.read_text(encoding="utf-8"))
        granularity = str(produced.get("timestamp_granularity") or "unknown")
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    if source_manifest:
        payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        payload["transcript_path"] = str(output)
        payload["transcript_origin"] = transcript_origin
        payload["transcript_model"] = model
        payload["transcript_timestamp_granularity"] = granularity
        payload["transcript_quality_tier"] = model_quality(
            "funasr" if backend == "funasr" else "mlx-whisper", model
        )["tier"]
        write_json(source_manifest, payload)
    timestamp_note = None
    if granularity == "coarse":
        timestamp_note = (
            "本次转写仅得到整段级时间戳（无逐句时间轴）。文稿中的时间戳只能作为章节近似导航，"
            "不可当作精确逐句时间，请在最终文档的“处理说明”中注明。"
        )
    print(json.dumps({
        "ok": True,
        "backend": backend,
        "transcript_path": str(output),
        "model": model,
        "quality_tier": model_quality(
            "funasr" if backend == "funasr" else "mlx-whisper", model
        )["tier"],
        "timestamp_granularity": granularity,
        "timestamp_note": timestamp_note,
        "language_hint": effective_language,
    }, ensure_ascii=False, indent=2))


def audio_duration_ms(path: str) -> int:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        text=True,
        capture_output=True,
    )
    try:
        return int(float(result.stdout.strip()) * 1000)
    except (ValueError, TypeError):
        return 0


def sensevoice_language(text: str, fallback: str | None) -> str:
    match = re.search(r"<\|(zh|en|yue|ja|ko|nospeech)\|>", text)
    return match.group(1) if match else fallback or "unknown"


def timestamp_granularity(segments: list[dict[str, Any]], fallback_single_segment: bool) -> str:
    """Classify how fine-grained the produced timestamps are.

    - "segment": multiple per-utterance segments with real timing (best case).
    - "coarse": only one segment spanning the whole audio, so any in-text
      timestamps must be treated as approximate navigation, not precise cues.
    """
    if fallback_single_segment or len(segments) <= 1:
        return "coarse"
    return "segment"


def funasr_worker(args: argparse.Namespace) -> None:
    try:
        from funasr import AutoModel
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
    except ImportError as error:
        raise AsrError("worker Python 中缺少 funasr") from error
    os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    model = AutoModel(
        model=args.model_path,
        vad_model=args.vad_path,
        vad_kwargs={"max_single_segment_time": 30000},
        device="cpu",
        disable_update=True,
    )
    options: dict[str, Any] = {
        "input": args.input,
        "cache": {},
        "language": args.language or "auto",
        "use_itn": True,
        "batch_size_s": 60,
        "merge_vad": True,
        "merge_length_s": 15,
        "output_timestamp": True,
    }
    results = model.generate(**options)
    if not results:
        raise AsrError("FunASR 没有返回结果")
    raw = results[0]
    raw_text = str(raw.get("text") or "")
    segments: list[dict[str, Any]] = []
    for item in raw.get("sentence_info") or []:
        text = rich_transcription_postprocess(str(item.get("text") or "")).strip()
        if text:
            segments.append({
                "start_ms": int(item.get("start") or 0),
                "end_ms": int(item.get("end") or 0),
                "text": text,
            })
    text = rich_transcription_postprocess(raw_text).strip()
    fallback_single_segment = False
    if not segments and text:
        segments = [{"start_ms": 0, "end_ms": audio_duration_ms(args.input), "text": text}]
        fallback_single_segment = True
    if not segments:
        raise AsrError("FunASR 没有返回可用文字")
    granularity = timestamp_granularity(segments, fallback_single_segment)
    payload = {
        "schema_version": 1,
        "created_at": utc_now(),
        "language": sensevoice_language(raw_text, args.language),
        "transcript_kind": "local-funasr-sensevoice",
        "source": str(Path(args.input).resolve()),
        "model": args.model_id,
        "quality_tier": "preferred",
        "segment_count": len(segments),
        "timestamp_granularity": granularity,
        "segments": segments,
        "text": "\n".join(item["text"] for item in segments),
    }
    write_json(Path(args.output).expanduser().resolve(), payload)


def mlx_worker(args: argparse.Namespace) -> None:
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TQDM_DISABLE", "1")
    try:
        import mlx_whisper
    except ImportError as error:
        raise AsrError("worker Python 中缺少 mlx_whisper") from error
    options: dict[str, Any] = {
        "path_or_hf_repo": args.model,
        "task": "transcribe",
        "word_timestamps": False,
        "condition_on_previous_text": True,
        "verbose": None,
    }
    if args.language:
        options["language"] = args.language
    result = mlx_whisper.transcribe(args.input, **options)
    segments = []
    for item in result.get("segments") or []:
        text = " ".join(str(item.get("text") or "").split())
        if text:
            segments.append({
                "start_ms": int(float(item.get("start") or 0) * 1000),
                "end_ms": int(float(item.get("end") or 0) * 1000),
                "text": text,
            })
    fallback_single_segment = False
    if not segments:
        text = " ".join(str(result.get("text") or "").split())
        if text:
            segments = [{"start_ms": 0, "end_ms": audio_duration_ms(args.input), "text": text}]
            fallback_single_segment = True
    if not segments:
        raise AsrError("MLX Whisper 没有返回可用文字")
    payload = {
        "schema_version": 1,
        "created_at": utc_now(),
        "language": result.get("language") or args.language or "unknown",
        "transcript_kind": "local-mlx-whisper",
        "source": str(Path(args.input).resolve()),
        "model": args.model,
        "quality_tier": model_quality("mlx-whisper", args.model)["tier"],
        "segment_count": len(segments),
        "timestamp_granularity": timestamp_granularity(segments, fallback_single_segment),
        "segments": segments,
        "text": "\n".join(item["text"] for item in segments),
    }
    write_json(Path(args.output).expanduser().resolve(), payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EchoScript local ASR detection and transcription")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    doctor_parser.set_defaults(handler=doctor)

    setup_parser = subparsers.add_parser("setup", help="Install a local runtime and, with approval, missing model files")
    setup_parser.add_argument("--backend", choices=("funasr", "mlx"), default="funasr")
    setup_parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    setup_parser.add_argument("--model")
    setup_parser.add_argument("--skip-model-download", action="store_true")
    setup_parser.add_argument("--upgrade", action="store_true")
    setup_parser.set_defaults(handler=setup)

    transcribe_parser = subparsers.add_parser("transcribe")
    transcribe_parser.add_argument("input", help="Audio file, source.json, or job directory")
    transcribe_parser.add_argument("--output", required=True)
    transcribe_parser.add_argument("--backend", choices=("auto", "funasr", "mlx"), default="auto")
    transcribe_parser.add_argument("--model")
    transcribe_parser.add_argument("--language", default="auto")
    transcribe_parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    transcribe_parser.add_argument(
        "--allow-low-quality-model",
        action="store_true",
        help="Allow a smoke-test-only model such as whisper-tiny after explicit user acceptance",
    )
    transcribe_parser.set_defaults(handler=transcribe)

    download_parser = subparsers.add_parser("_download_funasr")
    download_parser.add_argument("--cache-root", required=True)
    download_parser.add_argument("--model-id", action="append", required=True)
    download_parser.set_defaults(handler=download_funasr_worker)

    funasr_parser = subparsers.add_parser("_funasr_worker")
    funasr_parser.add_argument("input")
    funasr_parser.add_argument("output")
    funasr_parser.add_argument("--model-id", required=True)
    funasr_parser.add_argument("--model-path", required=True)
    funasr_parser.add_argument("--vad-path", required=True)
    funasr_parser.add_argument("--language")
    funasr_parser.set_defaults(handler=funasr_worker)

    mlx_parser = subparsers.add_parser("_mlx_worker")
    mlx_parser.add_argument("input")
    mlx_parser.add_argument("output")
    mlx_parser.add_argument("--model", required=True)
    mlx_parser.add_argument("--language")
    mlx_parser.set_defaults(handler=mlx_worker)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        args.handler(args)
        return 0
    except (AsrError, subprocess.CalledProcessError, json.JSONDecodeError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
