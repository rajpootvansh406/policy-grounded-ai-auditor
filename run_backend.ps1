# run_backend.ps1
#
# This starts the FastAPI backend in its own separate PowerShell window,
# completely independent of VS Code. This window will stay open even if
# you close VS Code entirely, switch terminal tabs, or open new ones.
#
# Usage: run this from your project root folder:
#   .\run_backend.ps1

$projectRoot = $PSScriptRoot

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$projectRoot\src'; & '$projectRoot\venv\Scripts\Activate.ps1'; uvicorn api:app --reload"
)

Write-Host "Backend starting in a new window. Look for it in your taskbar."
Write-Host "Leave that window open. Come back to THIS terminal for everything else."
