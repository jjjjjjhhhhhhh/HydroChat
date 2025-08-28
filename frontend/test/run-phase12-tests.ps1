# Phase 12 Frontend Test Runner (PowerShell)
Write-Host "🧪 Running HydroChat Phase 12 Frontend Tests..." -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# Change to frontend directory
Set-Location $PSScriptRoot\..

# Check if test dependencies exist
if (!(Test-Path "node_modules\@testing-library\react-native")) {
    Write-Host "📦 Installing test dependencies..." -ForegroundColor Yellow
    npm install
}

Write-Host ""
Write-Host "🔧 Running Jest tests directly..." -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green

# Run specific tests for Phase 12 using npx jest directly
npx jest --testMatch="<rootDir>/src/__tests__/**/*.test.{js,jsx,ts,tsx}" --verbose

Write-Host ""
Write-Host "📊 Test Coverage Report:" -ForegroundColor Blue
Write-Host "========================" -ForegroundColor Blue

npx jest --coverage --testMatch="<rootDir>/src/__tests__/**/*.test.{js,jsx,ts,tsx}" --silent

Write-Host ""
Write-Host "✅ Phase 12 test execution completed!" -ForegroundColor Green

# Pause to see results
Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
