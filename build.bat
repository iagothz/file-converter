@echo off
rem Gera FileConverter.exe na raiz do projeto
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --onefile --windowed --name FileConverter ^
    --collect-all tkinterdnd2 --distpath . --workpath build --specpath build gui.py || exit /b 1
echo.
echo Pronto: %~dp0FileConverter.exe
