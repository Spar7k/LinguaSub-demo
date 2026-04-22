# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)


def safe_collect(package_name, collector, *args, **kwargs):
    try:
        return collector(package_name, *args, **kwargs)
    except Exception:
        return []


packages_to_bundle = (
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "onnxruntime",
    "huggingface_hub",
)

binaries = []
datas = []
hiddenimports = []

for package_name in packages_to_bundle:
    hiddenimports += safe_collect(package_name, collect_submodules)
    datas += safe_collect(package_name, collect_data_files, include_py_files=True)
    binaries += safe_collect(package_name, collect_dynamic_libs)


a = Analysis(
    ['backend\\run_server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='linguasub-backend',
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
