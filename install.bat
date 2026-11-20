@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Installing dependencies (using official PyPI)
echo ============================================
python -m pip install --upgrade pip -i https://pypi.org/simple
python -m pip install -r requirements.txt -i https://pypi.org/simple
echo.
echo ============================================
echo   Installing mitmproxy CA certificate
echo   (a browser-like window may pop up - click trust/OK)
echo ============================================
python -m mitmproxy.tools.dump --version >nul 2>&1
python -c "from mitmproxy import certs; from mitmproxy.tools.dump import DumpMaster" 2>nul
echo.
echo If the certificate was not auto-installed, run manually:
echo   mitmdump -s mitm_addon.py
echo   then open http://mitm.it in your browser and install the Windows certificate.
echo.
pause
