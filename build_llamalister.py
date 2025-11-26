#!/usr/bin/env python3
"""
Build script for LlamaLister portable executable
"""
import os
import sys
import subprocess
from pathlib import Path

def build_exe():
    """Build the LlamaLister portable executable"""
    project_root = Path(__file__).parent
    llamalister_dir = project_root / "llamalister"
    script_path = llamalister_dir / "llamalister.py"

    if not script_path.exists():
        print(f"Error: Script not found at {script_path}")
        return False

    # Change to project root directory
    os.chdir(project_root)

    # PyInstaller command - directory based (faster and more reliable)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",  # Directory-based executable (faster than --onefile)
        "--windowed",  # No console window
        "--name", "LlamaLister",
        "--clean",  # Clean cache
        "--noconfirm",  # Don't ask for confirmation
        f"--add-data={llamalister_dir / 'listings.csv'};llamalister",
        f"--add-data={llamalister_dir / 'listings.json'};llamalister",
        f"--add-data={project_root / 'Core_AUA_System'};Core_AUA_System",
        "--hidden-import=pyautogui",
        "--hidden-import=pyperclip",
        "--hidden-import=pynput",
        "--hidden-import=pynput.mouse",
        "--hidden-import=pynput.keyboard",
        "--hidden-import=memory_service",
        "--hidden-import=strict_mode",
        "--hidden-import=tkinter.ttk",
        str(script_path)
    ]

    print("Building LlamaLister portable executable (directory-based)...")
    print(f"Command: {' '.join(cmd[:5])} ...")  # Show abbreviated command

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 minute timeout

        if result.returncode == 0:
            print("✅ Build successful!")
            print("Output:", result.stdout[-500:])  # Show last 500 chars of output

            # Check if executable was created
            exe_path = project_root / "dist" / "LlamaLister" / "LlamaLister.exe"
            if exe_path.exists():
                print(f"✅ Executable created: {exe_path}")
                print(f"File size: {exe_path.stat().st_size / (1024*1024):.1f} MB")

                # Create a simple launcher script
                launcher_path = project_root / "dist" / "Run_LlamaLister.bat"
                with open(launcher_path, 'w') as f:
                    f.write('@echo off\n')
                    f.write('cd /d "%~dp0\\LlamaLister"\n')
                    f.write('start LlamaLister.exe\n')
                print(f"✅ Launcher created: {launcher_path}")

                # Create a README for the portable version
                readme_path = project_root / "dist" / "README.txt"
                with open(readme_path, 'w') as f:
                    f.write("LlamaLister Portable\n")
                    f.write("====================\n\n")
                    f.write("This is a portable version of LlamaLister that can run on any Windows computer without installation.\n\n")
                    f.write("To run:\n")
                    f.write("1. Double-click 'Run_LlamaLister.bat' or\n")
                    f.write("2. Navigate to the 'LlamaLister' folder and double-click 'LlamaLister.exe'\n\n")
                    f.write("The application includes all necessary files and will save data in its own directory.\n")
                print(f"✅ README created: {readme_path}")

                return True
            else:
                print("❌ Executable not found in dist directory")
                return False
        else:
            print("❌ Build failed!")
            print("STDOUT:", result.stdout[-1000:])  # Show last 1000 chars
            print("STDERR:", result.stderr[-1000:])
            return False

    except subprocess.TimeoutExpired:
        print("❌ Build timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False

if __name__ == "__main__":
    success = build_exe()
    sys.exit(0 if success else 1)