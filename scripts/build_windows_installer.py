#!/usr/bin/env python3
"""
scripts/build_windows_installer.py — Standalone Windows .exe Packager for J.A.R.V.I.S. Mark 55 (Mark-LV)
Builds jarvis_2.exe directly on macOS using the embedded Windows x64 runtime and makensis (NSIS v3.12).

Copyright (c) 2026 Divyanshu Verma. All Rights Reserved.
Official YouTube: https://www.youtube.com/@divyanshu_sovereign_agent
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image

REPO_DIR = Path(__file__).resolve().parent.parent
BASE_RUNTIME_SRC = Path("/tmp/jarvis_base")
STAGE_DIR = Path("/tmp/jarvis_2_stage")
OUTPUT_EXE = Path("/Users/divyanshu/Desktop/jarvis_2.exe")
NSIS_COMPILER = "/opt/homebrew/bin/makensis"

print("=" * 76)
print("     🤖 PACKAGING STANDALONE J.A.R.V.I.S. MARK 55 FOR WINDOWS (jarvis_2.exe)")
print("     Copyright (c) 2026 Divyanshu Verma. All Rights Reserved.")
print("=" * 76)

# ── 1. Ensure Base Windows Runtime Exists ─────────────────────────────────────
print("\n[1/6] Verifying base Windows runtime...")
if not (BASE_RUNTIME_SRC / "python.exe").exists():
    print("      Extracting base Windows runtime from existing jarvis.exe...")
    BASE_RUNTIME_SRC.mkdir(parents=True, exist_ok=True)
    src_exe = Path("/Users/divyanshu/Desktop/jarvis.exe")
    if not src_exe.exists():
        src_exe = Path("/Users/divyanshu/Desktop/old jarvis by fatih/jarvis.exe")
    subprocess.run(["7zz", "x", str(src_exe), f"-o{BASE_RUNTIME_SRC}", "-y"], check=True, stdout=subprocess.DEVNULL)
print("      Base Windows Python 3.11 runtime ready.")

# ── 2. Create Staging Tree ───────────────────────────────────────────────────
print("\n[2/6] Staging runtime and libraries...")
if STAGE_DIR.exists():
    shutil.rmtree(STAGE_DIR)
STAGE_DIR.mkdir(parents=True, exist_ok=True)

# Copy base Windows runtime files (binaries, DLLs, pyds, python.exe, etc.)
for item in BASE_RUNTIME_SRC.iterdir():
    if item.name in ("$PLUGINSDIR", "Uninstall.exe", "JARVIS.exe", "Launch.bat", "Launch_Debug.bat"):
        continue
    # Do not copy old python project code
    if item.name in ("main.py", "ui.py", "actions", "core", "dashboard", "memory", "plugins", "config", "models", "README.md", "LICENSE", "LICENSE.txt", "requirements.txt"):
        continue
    dst = STAGE_DIR / item.name
    if item.is_dir():
        shutil.copytree(item, dst, symlinks=True)
    else:
        shutil.copy2(item, dst)

# Create models directory with .gitkeep
(STAGE_DIR / "models").mkdir(parents=True, exist_ok=True)
(STAGE_DIR / "models" / ".gitkeep").touch()

# Copy pure-Python extra packages from .venv
venv_dirs = list(REPO_DIR.glob(".venv/lib/python*/site-packages"))
if venv_dirs:
    venv_sp = venv_dirs[0]
    stage_sp = STAGE_DIR / "Lib" / "site-packages"
    stage_sp.mkdir(parents=True, exist_ok=True)
    
    pure_py_patterns = [
        "fastapi", "fastapi*", "starlette", "starlette*", "uvicorn", "uvicorn*",
        "ddgs", "ddgs*", "bs4", "beautifulsoup4*", "tinytuya", "tinytuya*",
        "paho", "paho_mqtt*", "openpyxl", "openpyxl*", "qrcode", "qrcode*",
        "send2trash", "send2trash*", "youtube_transcript_api", "youtube_transcript_api*",
        "yt_dlp", "yt_dlp*", "pptx", "docx", "pdfplumber", "pdfplumber*",
        "PyPDF2", "pdfminer*", "python_multipart*", "multipart*"
    ]
    
    copied_count = 0
    for pattern in pure_py_patterns:
        for match in venv_sp.glob(pattern):
            dest = stage_sp / match.name
            if not dest.exists():
                # Verify no macOS .so binary exists
                if match.is_dir():
                    if not list(match.glob("**/*.so")):
                        shutil.copytree(match, dest, symlinks=True)
                        copied_count += 1
                elif match.is_file() and not match.name.endswith(".so"):
                    shutil.copy2(match, dest)
                    copied_count += 1
    print(f"      Bundled {copied_count} additional pure-Python modules into site-packages.")

# ── 3. Copy Mark-LV (Mark 55) Codebase ────────────────────────────────────────
print("\n[3/6] Deploying Mark 55 codebase...")

def copy_project_tree(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".venv")]
        rel = Path(root).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f in (".DS_Store",) or f.endswith(".pyc") or f.endswith(".blend1"):
                continue
            shutil.copy2(Path(root) / f, target_dir / f)

# Copy directories
for folder in ["actions", "core", "dashboard", "memory", "plugins", "config"]:
    src_folder = REPO_DIR / folder
    if src_folder.exists():
        copy_project_tree(src_folder, STAGE_DIR / folder)

# Copy root files
for root_file in [
    "main.py", "ui.py", "demo_avatar.py", "requirements.txt", "setup.py",
    "CREDITS.md", "LICENSE", "README.md", "IronMan_Mark7_Gantry_Production.blend"
]:
    fpath = REPO_DIR / root_file
    if fpath.exists():
        shutil.copy2(fpath, STAGE_DIR / root_file)

# Fix jarvis.ico: convert to true multi-resolution Windows ICO
ico_dst = STAGE_DIR / "config" / "jarvis.ico"
src_ico = REPO_DIR / "config" / "jarvis.ico"
try:
    img = Image.open(src_ico)
    img.save(ico_dst, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("      Compiled multi-resolution Windows icon resource (config/jarvis.ico).")
except Exception as e:
    print(f"      Warning generating icon ({e}), falling back to base icon...")
    shutil.copy2(BASE_RUNTIME_SRC / "config" / "jarvis.ico", ico_dst)

# Default api_keys.json for Windows if not present
keys_dst = STAGE_DIR / "config" / "api_keys.json"
if not keys_dst.exists():
    example_src = REPO_DIR / "config" / "api_keys.json.example"
    if example_src.exists():
        shutil.copy2(example_src, keys_dst)

# ── 4. Clean Cache & Stale Files ──────────────────────────────────────────────
print("\n[4/7] Cleaning bytecode cache and macOS metadata from staging...")
cleaned_pyc = 0
for pyc in list(STAGE_DIR.rglob("*.pyc")):
    pyc.unlink()
    cleaned_pyc += 1
for pc in list(STAGE_DIR.rglob("__pycache__")):
    if pc.is_dir():
        shutil.rmtree(pc, ignore_errors=True)
for ds in list(STAGE_DIR.rglob(".DS_Store")):
    ds.unlink()
print(f"      Removed {cleaned_pyc} stale .pyc files and cached directories.")

# ── 5. Generate Windows Launchers ─────────────────────────────────────────────
print("\n[5/7] Creating Windows launchers (silent EXE & batch)...")

launch_bat = STAGE_DIR / "Launch.bat"
launch_bat.write_text(
    '@echo off\r\n'
    'cd /d "%~dp0"\r\n'
    'start "" "%~dp0pythonw.exe" "%~dp0main.py"\r\n',
    encoding="utf-8"
)

launch_debug_bat = STAGE_DIR / "Launch_Debug.bat"
launch_debug_bat.write_text(
    '@echo off\r\n'
    'cd /d "%~dp0"\r\n'
    'title J.A.R.V.I.S. Mark 55 - Diagnostic Console\r\n'
    'echo ====================================================================\r\n'
    'echo           🤖 J.A.R.V.I.S. (MARK 55) — DIAGNOSTIC MODE\r\n'
    'echo           Copyright (c) 2026 Divyanshu Verma. All Rights Reserved.\r\n'
    'echo ====================================================================\r\n'
    'echo.\r\n'
    'echo [*] Launching JARVIS in verbose diagnostic console mode...\r\n'
    '"%~dp0python.exe" "%~dp0main.py"\r\n'
    'echo.\r\n'
    'echo [*] Process finished or terminated.\r\n'
    'pause\r\n',
    encoding="utf-8"
)

# Compile silent JARVIS.exe launcher
launcher_nsi = Path("/tmp/jarvis_launcher.nsi")
launcher_nsi.write_text(f"""
Name "JARVIS"
OutFile "{STAGE_DIR / 'JARVIS.exe'}"
Icon "{ico_dst}"
SilentInstall silent
RequestExecutionLevel user

Section
  Exec '"$EXEDIR\\pythonw.exe" "$EXEDIR\\main.py"'
SectionEnd
""", encoding="utf-8")

subprocess.run([NSIS_COMPILER, str(launcher_nsi)], check=True, stdout=subprocess.DEVNULL)
print("      Compiled native silent launcher: JARVIS.exe")

# ── 6. Generate NSIS Installer Script ────────────────────────────────────────
print("\n[6/7] Building NSIS installer specification...")

installer_nsi = Path("/tmp/jarvis_mark55_installer.nsi")
installer_nsi.write_text(f"""
; ==============================================================================
; J.A.R.V.I.S. Mark 55 (Mark-LV) Standalone Windows Installer
; Copyright (c) 2026 Divyanshu Verma. All Rights Reserved.
; Official YouTube: https://www.youtube.com/@divyanshu_sovereign_agent
; ==============================================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; General Settings
Name "J.A.R.V.I.S. Mark 55"
OutFile "{OUTPUT_EXE}"
InstallDir "$PROGRAMFILES64\\JARVIS-Mark55"
InstallDirRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "InstallLocation"
RequestExecutionLevel admin

; Compression
SetCompressor /SOLID lzma

; Interface Configuration
!define MUI_ABORTWARNING
!define MUI_ICON "{ico_dst}"
!define MUI_UNICON "{ico_dst}"

; Installer Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

; Finish Page Options
!define MUI_FINISHPAGE_RUN "$INSTDIR\\JARVIS.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch J.A.R.V.I.S. Mark 55"
!insertmacro MUI_PAGE_FINISH

; Uninstaller Pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "English"

; Version Information
VIProductVersion "55.0.0.0"
VIFileVersion "55.0.0.0"
VIAddVersionKey "ProductName" "J.A.R.V.I.S. Mark 55 (Mark-LV)"
VIAddVersionKey "CompanyName" "Divyanshu Verma"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2026 Divyanshu Verma. All Rights Reserved."
VIAddVersionKey "FileDescription" "J.A.R.V.I.S. Mark 55 Standalone Installer"
VIAddVersionKey "FileVersion" "55.0.0.0"
VIAddVersionKey "ProductVersion" "55.0.0.0"

; Installation Section
Section "Install" SecInstall
    SetOutPath "$INSTDIR"
    File /r "{STAGE_DIR}/*"

    ; Create Uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    ; Desktop Shortcut
    SetShellVarContext all
    CreateShortcut "$DESKTOP\\JARVIS Mark 55.lnk" "$INSTDIR\\JARVIS.exe" "" "$INSTDIR\\config\\jarvis.ico" 0

    ; Start Menu Shortcuts
    CreateDirectory "$SMPROGRAMS\\JARVIS Mark 55"
    CreateShortcut "$SMPROGRAMS\\JARVIS Mark 55\\JARVIS Mark 55.lnk" "$INSTDIR\\JARVIS.exe" "" "$INSTDIR\\config\\jarvis.ico" 0
    CreateShortcut "$SMPROGRAMS\\JARVIS Mark 55\\Diagnostic Console.lnk" "$INSTDIR\\Launch_Debug.bat" "" "$INSTDIR\\config\\jarvis.ico" 0
    CreateShortcut "$SMPROGRAMS\\JARVIS Mark 55\\Uninstall.lnk" "$INSTDIR\\Uninstall.exe" "" "$INSTDIR\\Uninstall.exe" 0

    ; Windows Registry for Add/Remove Programs
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "DisplayName" "J.A.R.V.I.S. Mark 55 by Divyanshu Verma"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "DisplayIcon" "$INSTDIR\\config\\jarvis.ico"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "Publisher" "Divyanshu Verma"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "DisplayVersion" "55.0.0"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "InstallLocation" "$INSTDIR"
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "NoModify" 1
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55" "NoRepair" 1
SectionEnd

; Uninstallation Section
Section "Uninstall"
    SetShellVarContext all

    ; Remove Shortcuts
    Delete "$DESKTOP\\JARVIS Mark 55.lnk"
    RMDir /r "$SMPROGRAMS\\JARVIS Mark 55"

    ; Remove Registry Keys
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\JARVIS-Mark55"

    ; Remove Installation Files
    RMDir /r "$INSTDIR"
SectionEnd
""", encoding="utf-8")

# ── 7. Compile Final jarvis_2.exe ─────────────────────────────────────────────
print("\n[7/7] Compiling standalone Windows installer with makensis (LZMA solid compression)...")
if OUTPUT_EXE.exists():
    OUTPUT_EXE.unlink()

res = subprocess.run([NSIS_COMPILER, str(installer_nsi)], check=True)

if OUTPUT_EXE.exists():
    size_mb = OUTPUT_EXE.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 76)
    print(f"  ✅ SUCCESS: jarvis_2.exe generated at: {OUTPUT_EXE}")
    print(f"     Package Size: {size_mb:.2f} MB")
    print("=" * 76)
else:
    print("\n❌ Build finished but jarvis_2.exe was not found!")
    sys.exit(1)
