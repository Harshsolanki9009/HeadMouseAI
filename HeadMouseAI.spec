# -*- mode: python ; coding: utf-8 -*-
"""Optimized PyInstaller build specification for HeadMouseAI + Jadoo distribution."""

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = [
    ('assets/models/face_landmarker.task', 'assets/models'),
    ('assets/models/whisper/*', 'assets/models/whisper'),
    ('assets/bin/whisper/*', 'assets/bin/whisper'),
    ('assets/bin/agent-desktop/*', 'assets/bin/agent-desktop'),
    ('assets/graphics/*', 'assets/graphics'),
    ('assets/icons/*', 'assets/icons'),
    ('assets/images/*', 'assets/images'),
    ('config.toml', '.'),
    ('.env.example', '.'),
]

binaries = []

hiddenimports = [
    'sounddevice',
    'pyperclip',
    'pyautogui',
    'pyscreeze',
    'pygetwindow',
    'mouseinfo',
    'PIL',
    'toml',
    'ctypes',
    'psutil',
    'requests',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'mediapipe.tasks.python.vision.drawing_utils',
    'mediapipe.tasks.python.vision.drawing_styles',
]

excludes = [
    'tkinter',
    'IPython',
    'matplotlib.tests',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick',
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuick3D',
    'PySide6.QtQuick3DPhysics',
    'PySide6.QtQuick3DRuntimeRender',
    'PySide6.QtQuickControls2',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtDesigner',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtSql',
    'PySide6.QtTest',
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',
    'PySide6.QtSpatialAudio',
]

for pkg in ('mediapipe', 'cv2', 'PIL', 'psutil', 'sounddevice'):
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hiddenimports
    except Exception:
        pass

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

unused_binaries_lower = (
    'qt6webengine', 'qt6quick', 'qt6qml', 'qt6designer',
    'qt6pdf', 'qt6quick3d', 'qmlls.exe'
)
a.binaries = [x for x in a.binaries if not any(b in x[0].lower() for b in unused_binaries_lower)]
a.datas = [x for x in a.datas if not any(p in x[0].lower() for p in ('webengine', 'qtquick', 'designer'))]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HeadMouseAI',
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
    icon='assets/icons/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HeadMouseAI',
)
