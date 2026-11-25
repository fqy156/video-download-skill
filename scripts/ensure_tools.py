#!/usr/bin/env python3
"""跨平台工具定位/补齐脚本（Windows / macOS / Linux，x64 与 arm64）。

用法：
    python scripts/ensure_tools.py            # 输出 ffmpeg / ffprobe 路径（JSON）
    python scripts/ensure_tools.py --ytdlp    # 额外确保 yt-dlp 为最新版

查找顺序（找到即返回，绝不重复下载）：
  1. 系统 PATH 里的可执行文件（用户自己装过就用他的）
  2. 用户级缓存目录（可用环境变量 VIDEO_DOWNLOAD_TOOLS_DIR 覆盖）：
     - Windows: %LOCALAPPDATA%\\video-download\\bin
     - macOS:   ~/Library/Caches/video-download/bin
     - Linux:   $XDG_CACHE_HOME/video-download/bin（默认 ~/.cache/...）
  3. 通过 pip 安装 imageio-ffmpeg（PyPI 上有各平台预编译静态 ffmpeg 的 wheel），
     解出的 ffmpeg 复制进缓存，后续毫秒命中

设计原则：
  - ffmpeg 稳定、体积大，定位一次进缓存即可，不重复下载。
  - yt-dlp 变化快（周级更新，平台反爬一改版旧版即失效），不进缓存，每次装最新。
  - 不写死任何绝对路径：换机器、换系统、换 Agent 运行时都能工作。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def _default_cache_dir() -> Path:
    """各平台惯例的用户级缓存目录，绝不写进技能目录（避免污染仓库/发布包）。"""
    override = os.environ.get("VIDEO_DOWNLOAD_TOOLS_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "video-download" / "bin"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "video-download" / "bin"
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "video-download" / "bin"


CACHE_DIR = _default_cache_dir()
IS_WINDOWS = os.name == "nt"


def _exe(name: str) -> str:
    return f"{name}.exe" if IS_WINDOWS else name


def _which(name: str) -> Path | None:
    p = shutil.which(name)
    return Path(p) if p else None


def _find(name: str) -> tuple[Path | None, str | None]:
    """返回 (路径, 来源)。来源取值：PATH / cache。"""
    p = _which(name)
    if p:
        return p, "PATH"
    cached = CACHE_DIR / _exe(name)
    if cached.is_file():
        return cached, "cache"
    return None, None


def _pip_install(pkg: str, timeout: int = 600) -> None:
    """pip 安装到当前解释器环境。pip 会自动尊重 PIP_INDEX_URL 环境变量（可指向镜像）。"""
    cmd = [sys.executable, "-m", "pip", "install", "-q", "-U", pkg]
    subprocess.run(cmd, check=True, timeout=timeout)


def _imageio_ffmpeg_path() -> Path:
    """确保 imageio-ffmpeg 可用，并返回它提供的 ffmpeg 可执行文件路径。

    用子进程读取路径，避免同一进程内 pip 装完 import 缓存不刷新。
    """
    probe = "import imageio_ffmpeg,sys;sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())"
    r = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
    )
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip())
    _pip_install("imageio-ffmpeg")
    r = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"imageio-ffmpeg 安装后仍无法取到 ffmpeg：{r.stderr[:300]}")
    return Path(r.stdout.strip())


def ensure_ffmpeg() -> tuple[Path, str]:
    found, source = _find("ffmpeg")
    if found:
        return found, source  # type: ignore[return-value]

    exe = _imageio_ffmpeg_path()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / _exe("ffmpeg")
    if not dest.exists():
        shutil.copy2(exe, dest)
        if not IS_WINDOWS:
            dest.chmod(0o755)
    return dest, "imageio-ffmpeg"


def ensure_ffprobe(ffmpeg_path: Path) -> tuple[Path | None, str]:
    found, source = _find("ffprobe")
    if found:
        return found, source  # type: ignore[return-value]

    # imageio-ffmpeg 只提供 ffmpeg，ffprobe 通常与其同目录（系统安装包常见布局）
    sibling = ffmpeg_path.parent / _exe("ffprobe")
    if sibling.is_file():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dest = CACHE_DIR / _exe("ffprobe")
        if not dest.exists():
            shutil.copy2(sibling, dest)
            if not IS_WINDOWS:
                dest.chmod(0o755)
        return dest, "sibling"

    return None, "missing"  # 调用方改用 `ffmpeg -i` 解析媒体信息


def ensure_ytdlp() -> dict:
    """yt-dlp 不缓存：始终装最新版（平台反爬变化快）。"""
    cmd = [sys.executable, "-m", "yt_dlp", "--version"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        _pip_install("yt-dlp")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return {
        "launcher": [sys.executable, "-m", "yt_dlp"],
        "version": r.stdout.strip() if r.returncode == 0 else "unknown",
        "ok": r.returncode == 0,
    }


def main() -> None:
    ffmpeg, ffmpeg_src = ensure_ffmpeg()
    ffprobe, ffprobe_src = ensure_ffprobe(ffmpeg)

    result = {
        "platform": f"{sys.platform}",
        "ffmpeg": str(ffmpeg),
        "ffmpeg_source": ffmpeg_src,
        "ffprobe": str(ffprobe) if ffprobe else None,
        "ffprobe_source": ffprobe_src,
        "probe_hint": None
        if ffprobe
        else "未找到 ffprobe，改用 `ffmpeg -i <file>` 并从 stderr 解析时长/分辨率",
    }
    if "--ytdlp" in sys.argv:
        result["yt-dlp"] = ensure_ytdlp()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
