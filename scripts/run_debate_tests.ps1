# Run Debate Functional Test

Write-Host "Activate virtual environment..." -ForegroundColor Cyan
.\venv\Scripts\Activate.ps1

Write-Host "`n Run unit tests..." -ForegroundColor Cyan
python -m pytest tests/core/agents/test_researcher_debate.py -v

Write-Host "`n Run integration tests..." -ForegroundColor Cyan
python -m pytest tests/integration/test_debate_workflow.py -v -s

Write-Host "`n Test completed!" -ForegroundColor Green

