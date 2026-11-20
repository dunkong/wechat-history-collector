@echo off
chcp 65001 >nul
echo 正在强制关闭系统代理，恢复网络...
python -c "import winreg; k=winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',0,winreg.KEY_SET_VALUE); winreg.SetValueEx(k,'ProxyEnable',0,winreg.REG_DWORD,0); winreg.CloseKey(k); print('[OK] 系统代理已关闭，网络已恢复')"
echo.
pause
