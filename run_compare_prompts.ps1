# Run prompt word comparison script

Write-Host "Activate virtual environment..." -ForegroundColor Cyan
.\env\Scripts\Activate.ps1

Write-Host "`n Run prompt word comparison script..." -ForegroundColor Cyan
python scripts/compare_prompts.py

Write-Host "`n Finish!" -ForegroundColor Green

