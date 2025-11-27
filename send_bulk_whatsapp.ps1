# PowerShell Helper Script for Bulk WhatsApp Sender
# This script activates the virtual environment and runs the bulk sender

param(
    [Parameter(Mandatory=$true)]
    [string]$ExcelFile,
    
    [string]$TemplateName = "pune_clinic_offer",
    [string]$TemplateLanguage = "en_US",
    [string]$ImageId = "1223826332973821",
    [string]$ApiUrl = "https://graph.facebook.com/v22.0/367633743092037/messages"
)

# Get the script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
} else {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please ensure you're in the wb-crm directory and venv exists." -ForegroundColor Yellow
    exit 1
}

# Check if Excel file exists
if (-not (Test-Path $ExcelFile)) {
    Write-Host "Error: Excel file not found: $ExcelFile" -ForegroundColor Red
    exit 1
}

# Build command arguments
$args = @(
    "send_bulk_whatsapp.py",
    $ExcelFile,
    "--template-name", $TemplateName,
    "--template-language", $TemplateLanguage,
    "--image-id", $ImageId,
    "--api-url", $ApiUrl
)

# Run the script
Write-Host "`nStarting bulk WhatsApp sender..." -ForegroundColor Green
Write-Host "Excel File: $ExcelFile" -ForegroundColor Yellow
Write-Host "Template: $TemplateName" -ForegroundColor Yellow
Write-Host "`n" -ForegroundColor Yellow

python $args

# Check exit code
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nScript completed with errors. Check the output above." -ForegroundColor Red
    exit $LASTEXITCODE
} else {
    Write-Host "`nScript completed successfully!" -ForegroundColor Green
}

