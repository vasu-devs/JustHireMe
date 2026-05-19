from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname


_RELEASE_DOWNLOAD_BASE = "https://github.com/vasu-devs/JustHireMe/releases/latest/download"
_INSTALL_LOCK = threading.RLock()
_DLL_DIRS: set[str] = set()
_DLL_HANDLES: list[object] = []


def sys_platform() -> str:
    return platform.system().lower()


def _data_root() -> Path:
    configured = os.environ.get("JHM_APP_DATA_DIR")
    if configured:
        return Path(configured)
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys_platform() == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / "JustHireMe"


def vector_runtime_dir() -> Path:
    configured = os.environ.get("JHM_VECTOR_RUNTIME_DIR")
    if configured:
        return Path(configured)
    return _data_root() / "vector-runtime"


def vector_runtime_asset_name() -> str:
    system = sys_platform()
    if system == "windows":
        return "JustHireMe-vector-runtime-windows.zip"
    if system == "darwin":
        return "JustHireMe-vector-runtime-macos.zip"
    return "JustHireMe-vector-runtime-linux.zip"


def vector_runtime_url() -> str:
    return os.environ.get(
        "JHM_VECTOR_RUNTIME_URL",
        f"{_RELEASE_DOWNLOAD_BASE}/{vector_runtime_asset_name()}",
    )


def vector_runtime_roots(path: Path | None = None) -> list[Path]:
    root = path or vector_runtime_dir()
    return [
        root,
        root / "site-packages",
        root / "Lib" / "site-packages",
        root / "_internal",
    ]


def _add_dll_dir(path: Path) -> None:
    if os.name != "nt" or not path.exists() or not path.is_dir() or not hasattr(os, "add_dll_directory"):
        return
    key = str(path.resolve())
    if key in _DLL_DIRS:
        return
    _DLL_DIRS.add(key)
    _DLL_HANDLES.append(os.add_dll_directory(key))


def add_vector_runtime_to_path(path: Path | None = None) -> None:
    root = path or vector_runtime_dir()
    for candidate in vector_runtime_roots(root):
        if candidate.exists() and candidate.is_dir():
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)
            _add_dll_dir(candidate)
            _add_dll_dir(candidate / "pyarrow.libs")
            _add_dll_dir(candidate / "numpy.libs")


def vector_runtime_ready(path: Path | None = None) -> bool:
    add_vector_runtime_to_path(path)
    try:
        return bool(importlib.util.find_spec("lancedb") and importlib.util.find_spec("pyarrow"))
    except (ImportError, ValueError, AttributeError):
        return False


def _archive_payload_dir(extract_dir: Path) -> Path | None:
    candidates = [extract_dir, *[path for path in extract_dir.rglob("*") if path.is_dir()]]
    for candidate in candidates:
        if (candidate / "lancedb").exists() and (candidate / "pyarrow").exists():
            return candidate
    return None


def _safe_extract(archive_path: Path, extract_dir: Path) -> None:
    root = extract_dir.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (extract_dir / member.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("Downloaded vector runtime archive contains an unsafe path.")
        archive.extractall(extract_dir)


def _download(url: str, archive_path: Path) -> None:
    direct_path = Path(url)
    if direct_path.exists():
        shutil.copy2(direct_path, archive_path)
        return
    parsed = urlparse(url)
    if parsed.scheme in {"", "file"}:
        source = Path(url2pathname(parsed.path) if parsed.scheme == "file" else url)
        if os.name == "nt" and parsed.scheme == "file" and parsed.netloc:
            source = Path(f"//{parsed.netloc}{url2pathname(parsed.path)}")
        if source.exists():
            shutil.copy2(source, archive_path)
            return
    urllib.request.urlretrieve(url, archive_path)


def install_vector_runtime() -> Path:
    with _INSTALL_LOCK:
        runtime_dir = vector_runtime_dir()
        if vector_runtime_ready(runtime_dir):
            return runtime_dir

        runtime_dir.parent.mkdir(parents=True, exist_ok=True)
        url = vector_runtime_url()
        with tempfile.TemporaryDirectory(prefix="jhm-vector-runtime-") as tmp:
            tmp_dir = Path(tmp)
            archive_path = tmp_dir / vector_runtime_asset_name()
            try:
                _download(url, archive_path)
                extract_dir = tmp_dir / "extract"
                extract_dir.mkdir(parents=True, exist_ok=True)
                _safe_extract(archive_path, extract_dir)
            except Exception as exc:
                raise RuntimeError(
                    "The semantic matching engine must be installed before JustHireMe can continue. "
                    f"Could not download the vector runtime from {url}."
                ) from exc

            payload = _archive_payload_dir(extract_dir)
            if payload is None:
                raise RuntimeError("Downloaded vector runtime archive did not contain LanceDB and PyArrow.")

            if runtime_dir.exists():
                shutil.rmtree(runtime_dir)
            shutil.copytree(payload, runtime_dir)

        add_vector_runtime_to_path(runtime_dir)
        if not vector_runtime_ready(runtime_dir):
            raise RuntimeError("Vector runtime installation finished, but LanceDB or PyArrow could not be imported.")
        return runtime_dir


def vector_runtime_status() -> dict:
    runtime_dir = vector_runtime_dir()
    ready = vector_runtime_ready(runtime_dir)
    if ready and runtime_dir.exists():
        status = "installed"
    elif ready:
        status = "bundled"
    else:
        status = "missing"
    return {
        "status": status,
        "ready": ready,
        "required": True,
        "dir": str(runtime_dir),
        "asset": vector_runtime_asset_name(),
        "url": vector_runtime_url(),
    }
