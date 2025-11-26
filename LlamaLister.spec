# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\John\\Desktop\\llamagent\\llamamachinery-main\\llamamachinery-main\\llamalister\\llamalister.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\John\\Desktop\\llamagent\\llamamachinery-main\\llamamachinery-main\\llamalister\\listings.csv', 'llamalister'), ('C:\\Users\\John\\Desktop\\llamagent\\llamamachinery-main\\llamamachinery-main\\llamalister\\listings.json', 'llamalister'), ('C:\\Users\\John\\Desktop\\llamagent\\llamamachinery-main\\llamamachinery-main\\Core_AUA_System', 'Core_AUA_System')],
    hiddenimports=['pyautogui', 'pyperclip', 'pynput', 'pynput.mouse', 'pynput.keyboard', 'memory_service', 'strict_mode', 'tkinter.ttk'],
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
    [],
    exclude_binaries=True,
    name='LlamaLister',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LlamaLister',
)
