#!/usr/bin/env python3
"""Acquire metadata, subtitles, or audio for the EchoScript skill."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html as html_module
from html.parser import HTMLParser
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 EchoScript/1.0"
MEDIA_EXTENSIONS = {".mp3", ".wav", ".ogg", ".opus", ".m4a", ".mp4", ".aac", ".flac", ".webm", ".mov"}
TRANSCRIPT_EXTENSIONS = {".vtt", ".srt", ".txt", ".md"}
XIAOYUZHOU_PAGE_HOSTS = {"xiaoyuzhoufm.com", "www.xiaoyuzhoufm.com"}
XIAOYUZHOU_AUDIO_HOSTS = {"media.xyzcdn.net"}
LANGUAGE_PREFERENCES = ["zh-hans", "zh-cn", "zh", "zh-hant", "en"]


class IngestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(command: list[str], *, timeout: int = 3600, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError as error:
        raise IngestError(f"缺少命令：{command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise IngestError(f"命令执行超时：{command[0]}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        message = detail[-1] if detail else f"exit {result.returncode}"
        raise IngestError(f"{Path(command[0]).name} 执行失败：{message}")
    return result


def safe_name(value: str, fallback: str = "source") -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", str(value or ""))
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return (name[:100] or fallback).strip()


def request_bytes(url: str, *, referer: str | None = None, timeout: int = 30) -> tuple[bytes, str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            return response.read(), response.headers.get_content_type(), response.geturl()
    except HTTPError as error:
        raise IngestError(f"请求失败（HTTP {error.code}）：{url}") from error
    except URLError as error:
        raise IngestError(f"无法访问：{url}") from error


def request_json(url: str, *, referer: str | None = None, timeout: int = 30) -> dict[str, Any]:
    raw, _, _ = request_bytes(url, referer=referer, timeout=timeout)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IngestError(f"接口返回了无法解析的 JSON：{url}") from error
    if isinstance(value, dict) and "code" in value and value.get("code") not in (0, None):
        raise IngestError(str(value.get("message") or f"平台接口错误：{value.get('code')}"))
    return value


def timestamp_ms(value: str) -> int:
    text = value.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(text)
    return int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


def clean_caption_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_vtt_or_srt(text: str) -> list[dict[str, Any]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[dict[str, Any]] = []
    index = 0
    timing = re.compile(
        r"(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*"
        r"(?P<end>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})"
    )
    while index < len(lines):
        match = timing.search(lines[index])
        if not match:
            index += 1
            continue
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip():
            body.append(lines[index].strip())
            index += 1
        content = clean_caption_text(" ".join(body))
        if content and (not segments or segments[-1]["text"] != content):
            segments.append({
                "start_ms": timestamp_ms(match.group("start")),
                "end_ms": timestamp_ms(match.group("end")),
                "text": content,
            })
        index += 1
    return segments


def parse_youtube_json3(raw: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    segments: list[dict[str, Any]] = []
    for event in payload.get("events") or []:
        start = int(event.get("tStartMs") or 0)
        duration = int(event.get("dDurationMs") or 0)
        text = clean_caption_text("".join(str(item.get("utf8") or "") for item in event.get("segs") or []))
        if text and (not segments or segments[-1]["text"] != text):
            segments.append({"start_ms": start, "end_ms": start + duration, "text": text})
    return segments


def transcript_payload(
    segments: list[dict[str, Any]], *, language: str | None, kind: str, source: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "language": language or "unknown",
        "transcript_kind": kind,
        "source": source,
        "segment_count": len(segments),
        "segments": segments,
        "text": "\n".join(item["text"] for item in segments),
    }


def language_score(language: str) -> int:
    normalized = str(language or "").lower().replace("_", "-")
    for index, preferred in enumerate(LANGUAGE_PREFERENCES):
        if normalized == preferred or normalized.startswith(preferred + "-"):
            return index
    return len(LANGUAGE_PREFERENCES) + 10


def detect_source(source: str) -> str:
    local = Path(source).expanduser()
    if local.exists():
        return "local"
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return "youtube"
    if host in {"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"} or re.search(r"\bBV[0-9A-Za-z]{10}\b", source):
        return "bilibili"
    if host in XIAOYUZHOU_PAGE_HOSTS:
        return "xiaoyuzhou"
    raise IngestError("无法识别来源；请提供 YouTube、Bilibili、小宇宙链接或本地文件")


def ffprobe_metadata(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise IngestError("缺少 ffprobe，无法验证本地媒体")
    result = run([
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration,format_name",
        "-of", "json",
        str(path),
    ], timeout=60)
    payload = json.loads(result.stdout)
    format_info = payload.get("format") or {}
    return {
        "duration_seconds": round(float(format_info.get("duration") or 0), 3) or None,
        "format": format_info.get("format_name"),
        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }


def ingest_local(source: str, _: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise IngestError(f"本地文件不存在：{path}")
    suffix = path.suffix.lower()
    common = {
        "platform": "local",
        "title": path.stem,
        "author": "",
        "description": "",
        "published_at": "",
        "source_url": "",
        "local_source_path": str(path),
        "cover_url": "",
    }
    if suffix in TRANSCRIPT_EXTENSIONS:
        text = path.read_text(encoding="utf-8-sig")
        segments = parse_vtt_or_srt(text) if suffix in {".vtt", ".srt"} else [{"start_ms": 0, "end_ms": 0, "text": text.strip()}]
        if not segments or not any(item["text"] for item in segments):
            raise IngestError("本地文字稿为空")
        return {
            **common,
            "duration_seconds": None,
            "audio_path": None,
            "transcript_origin": "user-provided",
        }, transcript_payload(segments, language="unknown", kind="user-provided", source=str(path))
    if suffix not in MEDIA_EXTENSIONS:
        raise IngestError(f"不支持的本地文件格式：{suffix or '无扩展名'}")
    media = ffprobe_metadata(path)
    return {
        **common,
        **media,
        "audio_path": str(path),
        "transcript_origin": None,
    }, None


def yt_dlp_command(args: argparse.Namespace) -> list[str]:
    binary = shutil.which("yt-dlp")
    if not binary:
        raise IngestError("缺少 yt-dlp，无法处理 YouTube")
    command = [binary]
    if args.cookies_from_browser:
        command.extend(["--cookies-from-browser", args.cookies_from_browser])
    return command


def youtube_caption(metadata: dict[str, Any], source: str) -> tuple[dict[str, Any] | None, str | None]:
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for kind_priority, (kind, collection) in enumerate([
        ("manual-subtitle", metadata.get("subtitles") or {}),
        ("automatic-caption", metadata.get("automatic_captions") or {}),
    ]):
        for language, formats in collection.items():
            for format_priority, track in enumerate(formats or []):
                extension = str(track.get("ext") or "")
                extension_priority = {"vtt": 0, "json3": 1}.get(extension, 5)
                candidates.append((kind_priority, language_score(language), extension_priority + format_priority, kind, language, track))
    for _, _, _, kind, language, track in sorted(candidates, key=lambda item: item[:3]):
        url = track.get("url")
        if not url:
            continue
        try:
            raw, content_type, _ = request_bytes(str(url), referer=source)
        except IngestError:
            continue
        extension = str(track.get("ext") or "")
        segments = parse_youtube_json3(raw) if extension == "json3" or "json" in content_type else parse_vtt_or_srt(raw.decode("utf-8", errors="replace"))
        if segments:
            return transcript_payload(segments, language=language, kind=kind, source=source), language
    return None, None


def ingest_youtube(source: str, args: argparse.Namespace, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    command = yt_dlp_command(args) + ["--dump-single-json", "--no-playlist", "--skip-download", source]
    result = run(command, timeout=180)
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise IngestError("yt-dlp 没有返回有效的 YouTube 元数据") from error
    transcript, language = youtube_caption(metadata, source)
    audio_path: str | None = None
    if (not transcript or args.always_audio) and not args.metadata_only:
        media_dir = output_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        template = str(media_dir / "source.%(ext)s")
        download = yt_dlp_command(args) + [
            "--no-playlist", "-x", "--audio-format", "m4a", "--audio-quality", "0",
            "-o", template, source,
        ]
        run(download, timeout=7200)
        files = sorted(media_dir.glob("source.*"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not files:
            raise IngestError("YouTube 音频下载完成但没有找到输出文件")
        audio_path = str(files[0].resolve())
    thumbnails = metadata.get("thumbnails") or []
    largest = max(thumbnails, key=lambda item: int(item.get("width") or 0), default={})
    published = str(metadata.get("upload_date") or "")
    if re.fullmatch(r"\d{8}", published):
        published = f"{published[:4]}-{published[4:6]}-{published[6:]}"
    manifest = {
        "platform": "youtube",
        "source_url": metadata.get("webpage_url") or source,
        "title": metadata.get("title") or f"YouTube {metadata.get('id') or ''}".strip(),
        "author": metadata.get("channel") or metadata.get("uploader") or "",
        "description": metadata.get("description") or "",
        "published_at": published,
        "duration_seconds": metadata.get("duration"),
        "cover_url": metadata.get("thumbnail") or largest.get("url") or "",
        "language": language or metadata.get("language") or "unknown",
        "audio_path": audio_path,
        "transcript_origin": transcript.get("transcript_kind") if transcript else None,
        "platform_id": metadata.get("id"),
    }
    return manifest, transcript


def extract_bvid(source: str) -> str:
    match = re.search(r"\bBV[0-9A-Za-z]{10}\b", source)
    if not match:
        raise IngestError("没有识别到 Bilibili BV 号；短链接请先展开后重试")
    return match.group(0)


def bilibili_public_caption(bvid: str, cid: Any, source: str) -> tuple[dict[str, Any] | None, str | None]:
    endpoint = f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}"
    try:
        payload = request_json(endpoint, referer=f"https://www.bilibili.com/video/{bvid}/")
    except IngestError:
        return None, None
    tracks = ((payload.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
    ordered = sorted(tracks, key=lambda item: language_score(str(item.get("lan") or item.get("lan_doc") or "")))
    for track in ordered:
        url = str(track.get("subtitle_url") or track.get("subtitleUrl") or "")
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("https://"):
            continue
        try:
            data = request_json(url, referer=source)
        except IngestError:
            continue
        segments = []
        for item in data.get("body") or []:
            text = clean_caption_text(str(item.get("content") or ""))
            if text:
                segments.append({
                    "start_ms": int(float(item.get("from") or 0) * 1000),
                    "end_ms": int(float(item.get("to") or 0) * 1000),
                    "text": text,
                })
        if segments:
            language = str(track.get("lan") or track.get("lan_doc") or "unknown")
            return transcript_payload(segments, language=language, kind="platform-subtitle", source=source), language
    return None, None


def find_caption_segments(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str) and "-->" in value:
        return parse_vtt_or_srt(value)
    if isinstance(value, list):
        direct = []
        for item in value:
            if not isinstance(item, dict):
                continue
            text = clean_caption_text(str(item.get("text") or item.get("content") or item.get("body") or ""))
            if not text:
                continue
            start = item.get("start_ms", item.get("start", item.get("from", 0)))
            end = item.get("end_ms", item.get("end", item.get("to", start)))
            scale = 1 if "start_ms" in item or "end_ms" in item else 1000
            try:
                direct.append({"start_ms": int(float(start) * scale), "end_ms": int(float(end) * scale), "text": text})
            except (TypeError, ValueError):
                continue
        if direct:
            return direct
        for item in value:
            nested = find_caption_segments(item)
            if nested:
                return nested
    if isinstance(value, dict):
        for child in value.values():
            nested = find_caption_segments(child)
            if nested:
                return nested
    return []


def bilibili_opencli_caption(source: str) -> dict[str, Any] | None:
    binary = shutil.which("opencli")
    if not binary:
        return None
    try:
        result = run([binary, "bilibili", "subtitle", source, "-f", "json"], timeout=180)
    except IngestError:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        value = result.stdout
    segments = find_caption_segments(value)
    return transcript_payload(segments, language="zh", kind="browser-session-subtitle", source=source) if segments else None


def bilibili_audio(info: dict[str, Any], bvid: str, output_dir: Path) -> str:
    cid = info.get("cid") or (info.get("pages") or [{}])[0].get("cid")
    endpoint = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&fnval=16&fourk=1"
    payload = request_json(endpoint, referer=f"https://www.bilibili.com/video/{bvid}/")
    tracks = ((payload.get("data") or {}).get("dash") or {}).get("audio") or []
    tracks = [item for item in tracks if item.get("baseUrl") or item.get("base_url")]
    if not tracks:
        raise IngestError("Bilibili 没有返回可下载音频轨")
    track = max(tracks, key=lambda item: int(item.get("bandwidth") or 0))
    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    base = safe_name(f"{info.get('title') or bvid}-{bvid}")
    raw_path = media_dir / f"{base}.m4s"
    final_path = media_dir / f"{base}.m4a"
    curl = shutil.which("curl") or "/usr/bin/curl"
    environment = os.environ.copy()
    for name in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"]:
        environment[name] = ""
    run([
        curl, "-L", "--fail", "--retry", "3", "--retry-delay", "1",
        "--continue-at", "-", "--connect-timeout", "15", "--speed-limit", "1024",
        "--speed-time", "45", "--max-time", "2700", "--no-progress-meter",
        "-A", USER_AGENT, "-e", f"https://www.bilibili.com/video/{bvid}/",
        "-o", str(raw_path), str(track.get("baseUrl") or track.get("base_url")),
    ], timeout=2800, env=environment)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise IngestError(f"音频已下载到 {raw_path}，但缺少 ffmpeg，无法封装为 m4a")
    run([ffmpeg, "-y", "-v", "error", "-i", str(raw_path), "-vn", "-c", "copy", str(final_path)], timeout=300)
    raw_path.unlink(missing_ok=True)
    return str(final_path.resolve())


def ingest_bilibili(source: str, args: argparse.Namespace, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    bvid = extract_bvid(source)
    referer = f"https://www.bilibili.com/video/{bvid}/"
    payload = request_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", referer=referer)
    info = payload.get("data") or {}
    cid = info.get("cid") or (info.get("pages") or [{}])[0].get("cid")
    if not cid:
        raise IngestError("Bilibili 元数据缺少 cid")
    transcript, language = bilibili_public_caption(bvid, cid, referer)
    if not transcript and args.allow_browser_session:
        transcript = bilibili_opencli_caption(referer)
        language = "zh" if transcript else None
    audio_path: str | None = None
    if (not transcript or args.always_audio) and not args.metadata_only:
        audio_path = bilibili_audio(info, bvid, output_dir)
    published = datetime.fromtimestamp(int(info.get("pubdate") or 0), tz=timezone.utc).isoformat() if info.get("pubdate") else ""
    manifest = {
        "platform": "bilibili",
        "source_url": referer,
        "title": info.get("title") or bvid,
        "author": (info.get("owner") or {}).get("name") or "",
        "description": info.get("desc") or "",
        "published_at": published,
        "duration_seconds": info.get("duration"),
        "cover_url": info.get("pic") or "",
        "language": language or "unknown",
        "audio_path": audio_path,
        "transcript_origin": transcript.get("transcript_kind") if transcript else None,
        "platform_id": bvid,
    }
    return manifest, transcript


def normalize_xiaoyuzhou_episode_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname not in XIAOYUZHOU_PAGE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port
        or not re.fullmatch(r"/episode/[A-Za-z0-9_-]+/?", parsed.path)
    ):
        raise IngestError("请输入有效的小宇宙单集 HTTPS 链接")
    return parsed._replace(fragment="").geturl()


def normalize_xiaoyuzhou_audio_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname not in XIAOYUZHOU_AUDIO_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port
    ):
        raise IngestError("小宇宙页面返回了不受信任的音频地址")
    return parsed._replace(fragment="").geturl()


class SafeXiaoyuzhouRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, file_pointer: Any, code: int, message: str, headers: Any, new_url: str) -> Request | None:
        safe_url = normalize_xiaoyuzhou_episode_url(urljoin(request.full_url, new_url))
        return super().redirect_request(request, file_pointer, code, message, headers, safe_url)


class PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta" and values.get("content"):
            key = values.get("property") or values.get("name")
            if key:
                self.metadata[key.lower()] = html_module.unescape(values["content"])
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def script_json(page: str, identifier: str) -> Any:
    escaped = re.escape(identifier)
    pattern = re.compile(rf"<script[^>]+(?:id|name)=[\"']{escaped}[\"'][^>]*>([\s\S]*?)</script>", re.I)
    match = pattern.search(page)
    if not match:
        return None
    try:
        return json.loads(html_module.unescape(match.group(1).strip()))
    except json.JSONDecodeError:
        return None


def find_episode(value: Any) -> dict[str, Any] | None:
    queue = [value]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if not isinstance(current, (dict, list)) or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, dict):
            if (current.get("title") or current.get("name")) and (
                ((current.get("enclosure") or {}).get("url"))
                or current.get("audioUrl")
                or ((current.get("media") or {}).get("url"))
            ):
                return current
            queue.extend(current.values())
        else:
            queue.extend(current)
    return None


def pick(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = clean_caption_text(str(value))
        if text:
            return text
    return ""


def ingest_xiaoyuzhou(source: str, args: argparse.Namespace, output_dir: Path) -> tuple[dict[str, Any], None]:
    safe_source = normalize_xiaoyuzhou_episode_url(source)
    opener = build_opener(SafeXiaoyuzhouRedirect())
    try:
        with opener.open(Request(safe_source, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}), timeout=20) as response:
            final_url = normalize_xiaoyuzhou_episode_url(response.geturl())
            page = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as error:
        raise IngestError("小宇宙页面访问失败") from error
    parser = PageMetadataParser()
    parser.feed(page)
    next_data = script_json(page, "__NEXT_DATA__")
    schema = script_json(page, "schema:podcast-show") or {}
    episode = find_episode(next_data) or {}
    podcast = episode.get("podcast") or episode.get("podcastInfo") or {}
    enclosure = episode.get("enclosure") or {}
    media = episode.get("media") or {}
    associated = schema.get("associatedMedia") or {}
    audio_url = pick(
        enclosure.get("url"),
        (media.get("source") or {}).get("url"),
        media.get("url"),
        (episode.get("audio") or {}).get("url"),
        episode.get("audioUrl"),
        associated.get("contentUrl"),
        parser.metadata.get("og:audio"),
    )
    audio_url = normalize_xiaoyuzhou_audio_url(audio_url)
    title = pick(episode.get("title"), episode.get("name"), schema.get("name"), parser.metadata.get("og:title"), "".join(parser.title_parts).split("|")[0])
    if not title:
        raise IngestError("没有获取到小宇宙节目标题")
    duration = episode.get("duration") or episode.get("durationSec")
    try:
        duration_value = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_value = None
    audio_path: str | None = None
    if not args.metadata_only:
        media_dir = output_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        extension = Path(urlparse(audio_url).path).suffix.lower()
        if extension not in MEDIA_EXTENSIONS:
            extension = ".m4a"
        destination = media_dir / f"{safe_name(title)}{extension}"
        curl = shutil.which("curl") or "/usr/bin/curl"
        run([
            curl, "--fail", "--location", "--max-redirs", "0", "--proto", "=https",
            "--connect-timeout", "15", "--retry", "3", "--retry-delay", "1",
            "--max-time", "7200", "--no-progress-meter", "-A", USER_AGENT, "-e", final_url,
            "-o", str(destination), audio_url,
        ], timeout=7250)
        audio_path = str(destination.resolve())
    manifest = {
        "platform": "xiaoyuzhou",
        "source_url": final_url,
        "title": title,
        "author": pick(podcast.get("title"), podcast.get("name"), (schema.get("partOfSeries") or {}).get("name"), "小宇宙"),
        "description": pick(episode.get("description"), episode.get("shownotes"), schema.get("description"), parser.metadata.get("og:description"), parser.metadata.get("description")),
        "published_at": pick(episode.get("pubDate"), episode.get("publishedAt"), episode.get("createdAt"), schema.get("datePublished")),
        "duration_seconds": duration_value,
        "cover_url": pick(parser.metadata.get("og:image"), (episode.get("image") or {}).get("url"), episode.get("coverUrl")),
        "language": "unknown",
        "audio_path": audio_path,
        "transcript_origin": None,
        "platform_id": final_url.rstrip("/").split("/")[-1],
    }
    return manifest, None


def ingest(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    platform = detect_source(args.source)
    if platform == "local":
        manifest, transcript = ingest_local(args.source, args)
    elif platform == "youtube":
        manifest, transcript = ingest_youtube(args.source, args, output_dir)
    elif platform == "bilibili":
        manifest, transcript = ingest_bilibili(args.source, args, output_dir)
    else:
        manifest, transcript = ingest_xiaoyuzhou(args.source, args, output_dir)
    transcript_path = output_dir / "transcript.raw.json" if transcript else None
    if transcript and transcript_path:
        write_json(transcript_path, transcript)
    source_payload = {
        "schema_version": 1,
        "created_at": utc_now(),
        **manifest,
        "transcript_path": str(transcript_path.resolve()) if transcript_path else None,
    }
    write_json(output_dir / "source.json", source_payload)
    print(json.dumps({
        "ok": True,
        "platform": platform,
        "source_manifest": str((output_dir / "source.json").resolve()),
        "transcript_path": source_payload["transcript_path"],
        "audio_path": source_payload.get("audio_path"),
        "transcript_origin": source_payload.get("transcript_origin"),
    }, ensure_ascii=False, indent=2))


def doctor(_: argparse.Namespace) -> None:
    tools = {name: shutil.which(name) for name in ["ffmpeg", "ffprobe", "curl", "yt-dlp", "opencli"]}
    print(json.dumps({
        "ok": all(tools[name] for name in ["ffmpeg", "ffprobe", "curl"]),
        "tools": tools,
        "platforms": {
            "local": bool(tools["ffprobe"]),
            "youtube": bool(tools["yt-dlp"]),
            "bilibili_public": bool(tools["curl"] and tools["ffmpeg"]),
            "bilibili_browser_subtitles": bool(tools["opencli"]),
            "xiaoyuzhou": bool(tools["curl"]),
        },
    }, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EchoScript media and subtitle acquisition")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor_parser = subparsers.add_parser("doctor", help="Inspect local acquisition tools")
    doctor_parser.set_defaults(handler=doctor)
    ingest_parser = subparsers.add_parser("ingest", help="Acquire metadata, subtitles, or audio")
    ingest_parser.add_argument("source")
    ingest_parser.add_argument("--output-dir", required=True)
    ingest_parser.add_argument("--metadata-only", action="store_true", help="Resolve metadata without downloading audio")
    ingest_parser.add_argument("--always-audio", action="store_true", help="Download audio even when subtitles are found")
    ingest_parser.add_argument("--allow-browser-session", action="store_true", help="Allow OpenCLI to read Bilibili subtitles from the current Chrome session")
    ingest_parser.add_argument("--cookies-from-browser", metavar="BROWSER", help="Allow yt-dlp to read an explicitly approved browser cookie store")
    ingest_parser.set_defaults(handler=ingest)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
        return 0
    except IngestError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

