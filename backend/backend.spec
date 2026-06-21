# -*- mode: python ; coding: utf-8 -*-
import sys
import site
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
backend_root = Path("backend").resolve()
if not (backend_root / "main.py").exists():
    backend_root = Path(".").resolve()
# Keep every desktop installer slim: heavy vector/browser runtimes are shipped
# through the first-run runtime pack, not as PyInstaller onedir payloads.
onedir_sidecar = False
macos_entitlements = backend_root.parent / "src-tauri" / "macos-entitlements.plist"
exe_kwargs = {}
if sys.platform == "darwin":
    exe_kwargs["codesign_identity"] = os.environ.get("JHM_MACOS_CODESIGN_IDENTITY", "-")
    if macos_entitlements.exists():
        exe_kwargs["entitlements_file"] = str(macos_entitlements)
if sys.platform == "win32":
    venv_site_packages = backend_root / ".venv" / "Lib" / "site-packages"
else:
    venv_site_packages = backend_root / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
site.getusersitepackages = lambda: str(venv_site_packages)

release_features = {
    feature.strip().lower()
    for feature in os.environ.get("JHM_RELEASE_FEATURES", "core,graph,browser").split(",")
    if feature.strip()
}
include_browser = "browser" in release_features or "all" in release_features
include_vector = "vector" in release_features or "all" in release_features
include_graph = "graph" in release_features or "all" in release_features

hidden = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi", "fastapi.middleware.cors",
    "anthropic", "openai", "instructor",
    "langgraph", "langgraph.graph",
    "apscheduler", "apscheduler.schedulers.asyncio",
    "unittest", "pydoc",
    "defusedxml", "defusedxml.ElementTree",
    "fpdf", "fpdf.fpdf", "fpdf.image_parsing", "fpdf.output",
    "fpdf.sign", "fpdf.svg",
    "pypdf", "markdown",
    "tenacity",
    "graph",
    # certifi ships the CA bundle the first-run runtime-pack downloader points
    # OpenSSL at; macOS sidecar Python has no system CA store. See
    # data/vector/runtime.py::_https_ssl_context.
    "certifi",
    "gateway",
    "graph_service", "graph_service.stats", "graph_service.helpers",
    "llm", "logger",
] + collect_submodules("data") + collect_submodules("gateway") + collect_submodules("graph_service") + (
    # Domain packages loaded dynamically via import_module() (api/dependencies.py
    # DI, gateway/discovery_config.py -> discovery.targets, lazy `from graph` /
    # `from help` imports). PyInstaller's static analysis can't follow those, so
    # collect them explicitly — otherwise the frozen sidecar dies at startup with
    # ModuleNotFoundError (e.g. "No module named 'discovery'").
    collect_submodules("core")
    + collect_submodules("discovery")
    + collect_submodules("ranking")
    + collect_submodules("generation")
    + collect_submodules("profile")
    + collect_submodules("automation")
    + collect_submodules("help")
    + collect_submodules("llm")
)

if include_graph:
    hidden += ["kuzu"]

# ONNX local embeddings (lightweight, ~22 MB total)
try:
    import onnxruntime
    hidden += ["onnxruntime"]
except ImportError:
    pass
try:
    import tokenizers
    hidden += ["tokenizers"]
except ImportError:
    pass

if include_browser:
    hidden += collect_submodules("playwright")

if include_vector:
    hidden += ["lancedb", "pyarrow"] + collect_submodules(
        "lancedb",
        filter=lambda name: ".tests" not in name and not name.endswith(".conftest"),
    ) + collect_submodules(
        "pyarrow",
        filter=lambda name: ".tests" not in name and not name.endswith(".conftest"),
    )

datas = (
    [(str(backend_root / "data" / "sqlite" / "migrations"), "data/sqlite/migrations")]
    # C3: ship the profile import template so the /ingest/profile/template
    # endpoint can read it in a packaged build.
    + [(str(backend_root / "data" / "profile_schema_example.json"), "data")]
    # Bundle the models.dev snapshot so the model picker is fully populated
    # offline / before the first live refresh in a packaged build.
    + [(str(backend_root / "llm" / "models_snapshot.json"), "llm")]
    # certifi's cacert.pem must be bundled so the first-run runtime-pack
    # downloader can verify GitHub's TLS cert on macOS.
    + collect_data_files("certifi")
)

if include_browser:
    datas += collect_data_files("playwright")

if include_vector:
    datas += collect_data_files("lancedb") + collect_data_files("pyarrow")

excludes = [
    "IPython", "notebook", "jupyter", "docutils", "sphinx",
    "setuptools", "pip", "wheel", "pkg_resources",
    "xmlrpc", "lib2to3",
    "pyarrow.tests", "lancedb.tests",
    "tkinter", "matplotlib", "PIL", "cv2",
    "pytest", "tensorboard",
    "sentence_transformers", "transformers",
    "torch", "torch.distributed",
    "sklearn", "scipy",
]

if not include_browser:
    excludes += ["playwright"]

if not include_vector:
    excludes += ["lancedb", "pyarrow"]

a = Analysis(
    ["main.py"],
    pathex=[str(backend_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe_inputs = [] if onedir_sidecar else [a.binaries, a.zipfiles, a.datas]

exe = EXE(
    pyz, a.scripts,
    *exe_inputs,
    exclude_binaries=onedir_sidecar,
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Tauri launches sidecars with CREATE_NO_WINDOW on Windows while still
    # capturing stdout/stderr. Keep the console subsystem so the app can read
    # the JHM_TOKEN/PORT startup handshake from the packaged sidecar.
    console=True,
    **exe_kwargs,
)

if onedir_sidecar:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name="backend",
    )
