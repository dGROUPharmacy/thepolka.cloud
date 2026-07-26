@echo off
setlocal
set "FAIRE_INSTALL=%ProgramData%\FaireOS"
if not exist "%FAIRE_INSTALL%" mkdir "%FAIRE_INSTALL%"
xcopy "%~dp0*" "%FAIRE_INSTALL%\" /E /I /H /Y /Q >nul
if errorlevel 1 (
  echo FAIRE OS could not copy its runtime to "%FAIRE_INSTALL%".
  pause
  exit /b 1
)
copy /Y "%FAIRE_INSTALL%\FaireOS.scr" "%WINDIR%\System32\FaireOS.scr" >nul
if errorlevel 1 (
  echo FAIRE OS needs administrator approval to install as a Windows screensaver.
  pause
  exit /b 1
)
echo FAIRE OS was installed. Select FaireOS in Screen Saver Settings.
start "" control.exe desk.cpl,,@screensaver
endlocal
