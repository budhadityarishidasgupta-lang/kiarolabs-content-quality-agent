@echo off
setlocal
cd /d "%~dp0"
C:\Users\DND\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe main.py --mode all --dry-run
