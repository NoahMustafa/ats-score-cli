# PyInstaller spec — single-file `tool` binary (tool.exe on Windows).
# Build:  pyinstaller tool.spec   (per-OS; PyInstaller cannot cross-compile)
#
# All bundled data lands under ats_score/data so it matches the dev layout that
# paths.bundled_path() expects (sys._MEIPASS/ats_score/data/...).

# V1: the embedding model is NOT bundled. JD-match is disabled in this build
# (core._model_available() returns False when data/potion-8M is absent). We
# bundle only the skills taxonomy, which is taxonomy-only and needs no model.
# Spelling was removed, so words_alpha.txt is not bundled either.
datas = [("ats_score/data/skills.txt", "ats_score/data")]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Model stack + spelling are unused in V1 — exclude to shrink the binary.
    # They import lazily inside functions that V1 never calls, so this is safe.
    excludes=["tkinter", "matplotlib", "IPython", "pytest",
              "model2vec", "tokenizers", "safetensors", "spellchecker"],
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
