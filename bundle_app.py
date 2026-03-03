import os
import subprocess
import sys

def bundle():
    print("[*] Starting BlockVote Bundling Process...")
    
    # 1. Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("[*] PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Define the PyInstaller command
    # --onefile: Create a single executable
    # --add-data: Include the templates folder (format: source;destination for Windows)
    # --name: Final name of the .exe
    # --clean: Clean cache before build
    
    cmd = [
        "pyinstaller",
        "--onefile",
        "--add-data", "templates;templates",
        "--name", "admin_node",
        "--clean",
        "app.py"
    ]

    print(f"[*] Executing: {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        print("\n" + "="*40)
        print("SUCCESS! Your standalone executable is in: dist/admin_node.exe")
        print("="*40)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Bundling failed: {e}")

if __name__ == "__main__":
    bundle()
