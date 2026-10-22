@echo off
rem Double-click in Explorer to serve the learning site and the admin panel
rem (uv run learnkb-serve) and open http://localhost:8000. Close this window, or
rem press Ctrl+C, to stop the server.
setlocal
cd /d "%~dp0"
set PORT=8000

rem Already running (another window, or started from a terminal): just open it.
curl -sf -o nul -I http://localhost:%PORT%/admin/ >nul 2>nul
if not errorlevel 1 (
  echo The learning site is already running; opening it.
  start "" http://localhost:%PORT%/
  exit /b 0
)

rem Look where the uv installer puts uv, in case PATH hasn't been refreshed yet.
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo.
  echo uv isn't installed. Install it from https://docs.astral.sh/uv/ and try again.
  echo.
  pause
  exit /b 1
)

echo Learning tool
echo.

uv run learnkb-serve --open --port %PORT%
if errorlevel 1 (
  echo.
  echo The server stopped with an error, see above.
  echo.
  pause
  exit /b 1
)
