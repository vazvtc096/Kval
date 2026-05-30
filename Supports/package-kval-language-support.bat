@echo off
setlocal

cd /d "%~dp0Kval-language-support" || (
  echo Failed to enter Kval-language-support directory.
  exit /b 1
)

call npm install || exit /b 1
call npm run compile || exit /b 1
call npm run vsix || exit /b 1

echo.
echo Packaging finished.
endlocal
