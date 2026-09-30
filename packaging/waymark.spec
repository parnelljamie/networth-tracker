# Phase 9: PyInstaller one-folder build. Run via scripts/build-installer.ps1, or directly:
#   cd backend; uv run pyinstaller ../packaging/waymark.spec --noconfirm --clean
#
# --onedir (not --onefile): starts faster and triggers fewer antivirus false positives; the
# Inno Setup installer wraps the resulting folder.
from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()  # noqa: F821 - injected by PyInstaller
REPO_ROOT = SPEC_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

sys.path.insert(0, str(BACKEND_DIR))
from app import __version__  # noqa: E402

datas = [
    (str(FRONTEND_DIST), "frontend/dist"),
    (str(BACKEND_DIR / "alembic"), "backend/alembic"),
    (str(BACKEND_DIR / "alembic.ini"), "backend"),
]
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

for package in ("yfinance",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

datas += collect_data_files("tzdata")
binaries += collect_dynamic_libs("curl_cffi")
hiddenimports += collect_submodules("apscheduler")

IS_LINUX = sys.platform.startswith("linux")
excludes = []
if IS_LINUX:
    # pywebview picks its backend at runtime and reaches Qt through qtpy, so PyInstaller can't
    # see these imports; list them so PySide6's hooks bundle Qt WebEngine and its helper process.
    hiddenimports += [
        "webview.platforms.qt",
        "qtpy",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    ]
    # Only PySide6 is installed, but qtpy probes for the others; keep them out explicitly.
    excludes += ["PyQt5", "PyQt6", "PySide2", "webview.platforms.gtk"]
    # Qt modules the window never uses. Leaving them out saves ~100 MB and their extra system
    # dependencies (PulseAudio for multimedia/speech). QtQuick and QtQml stay: WebEngine links them.
    excludes += [
        f"PySide6.{m}"
        for m in (
            "QtMultimedia", "QtMultimediaWidgets", "QtSpatialAudio", "QtTextToSpeech",
            "Qt3DCore", "Qt3DRender", "Qt3DInput", "Qt3DLogic", "Qt3DAnimation", "Qt3DExtras",
            "QtQuick3D", "QtCharts", "QtDataVisualization", "QtGraphs", "QtBluetooth", "QtNfc",
            "QtSensors", "QtSerialPort", "QtSerialBus", "QtLocation", "QtPositioning",
            "QtRemoteObjects", "QtScxml", "QtSql", "QtTest", "QtDesigner", "QtUiTools", "QtHelp",
            "QtPdf", "QtPdfWidgets", "QtHttpServer", "QtWebSockets", "QtWebView",
        )
    ]

# Windows EXE version resource, built from the single version source (app/__init__.py),
# so Explorer's Properties dialog and any version-sniffing tools agree with Settings and
# /api/health. Skipped gracefully if PyInstaller's win32 helpers aren't available (non-Windows).
version_file = None
try:
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    _parts = (__version__.split(".") + ["0", "0", "0"])[:4]
    _tuple = tuple(int(p) if p.isdigit() else 0 for p in _parts)
    version_file = str(SPEC_DIR / "_version_info.txt")
    vs = VSVersionInfo(
        ffi=FixedFileInfo(filevers=_tuple, prodvers=_tuple),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "Waymark"),
                            StringStruct("FileDescription", "Waymark net worth tracker"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("ProductName", "Waymark"),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    Path(version_file).write_text(str(vs))
except Exception as exc:  # pragma: no cover - non-Windows dev machines
    print(f"Skipping EXE version resource ({exc})")

block_cipher = None

a = Analysis(
    [str(BACKEND_DIR / "app" / "launcher.py")],
    pathex=[str(BACKEND_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
if IS_LINUX:
    # PyInstaller also copies the build machine's own system libraries (glib, gnutls, libidn2 ...).
    # Bundled copies from the build's Ubuntu then shadow the user's newer ones and can need
    # libraries that release no longer has (22.04's glib needs libpcre.so.3, gone in 24.04), so
    # take these from the installed system instead; the .deb's Depends line guarantees them.
    _system = [b for b in a.binaries if b[1].startswith(("/lib/", "/usr/lib/", "/lib64/", "/usr/lib64/"))]
    for dest, src, _kind in _system:
        print(f"Using the system's copy of {dest} (not bundling {src})")
    a.binaries = [b for b in a.binaries if b not in _system]
    # Qt plugins and QML for the excluded modules still get collected as data; drop them too.
    _unused = ("multimedia", "texttospeech", "spatialaudio", "Quick3D", "Qt63D", "qt3d", "VirtualKeyboard", "sqldrivers",
               "QtGraphs", "libQt6Graphs", "Scene2D", "Scene3D")
    a.binaries = [b for b in a.binaries if not any(u.lower() in b[0].lower() for u in _unused)]
    a.datas = [d for d in a.datas if not any(u.lower() in d[0].lower() for u in _unused)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    # Linux convention is a lowercase command (/usr/bin/waymark); Windows has Waymark.exe.
    name="waymark" if IS_LINUX else "Waymark",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None if IS_LINUX else str(SPEC_DIR / "waymark.ico"),
    version=None if IS_LINUX else version_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Waymark",
)

print(f"Building Waymark {__version__}")
