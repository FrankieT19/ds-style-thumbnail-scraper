$ErrorActionPreference = "Stop"

python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller "DS Style Thumbnail Scraper.spec"

Write-Host ""
Write-Host "Built dist\DS Style Thumbnail Scraper.exe"
