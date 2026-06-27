# PyInstaller spec — single-file `tool` binary (tool.exe on Windows).
# Build:  pyinstaller tool.spec   (per-OS; PyInstaller cannot cross-compile)
#
# All bundled data lands under ats_score/data so it matches the dev layout that
# paths.bundled_path() expects (sys._MEIPASS/ats_score/data/...).

from PyInstaller.utils.hooks import copy_metadata

# Bundle the skills taxonomy and the embedding model (Tier 1 + Tier 2 JD match).
datas = [
    ("ats_score/data/skills.txt", "ats_score/data"),
    ("ats_score/data/potion-8M", "ats_score/data/potion-8M"),
]
# Some deps look up their own version via importlib.metadata at import time.
for pkg in ("model2vec", "tokenizers", "safetensors", "numpy"):
    datas += copy_metadata(pkg)

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["model2vec", "tokenizers", "safetensors"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Spelling is gone in V1; tkinter/matplotlib/IPython/pytest are unused.
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "spellchecker"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
