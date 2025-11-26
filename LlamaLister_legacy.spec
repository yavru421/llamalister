# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['llamalister.py'],
    pathex=['C:\\Users\\John\\Desktop\\llamagent\\llamamachinery-main\\llamamachinery-main\\Core_AUA_System\\src'],
    binaries=[],
    datas=[('listings.csv', '.')],
    hiddenimports=['memory_service', 'sqlite3'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'matplotlib', 'IPython'],
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
    name='LlamaLister',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='NONE',
)
