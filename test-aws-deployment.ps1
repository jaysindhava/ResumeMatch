#!/usr/bin/env pwsh
# =============================================================================
# test-aws-deployment.ps1  —  End-to-end verification of the AWS deployment
#
# Usage:  .\test-aws-deployment.ps1 -ApiUrl "http://<public-ip>:8000"
# =============================================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$ApiUrl,

    [string]$Region  = "ap-south-1",
    [string]$AppName = "resumematch"
)

$AWS = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"

function Log   { param([string]$msg) Write-Host "`n[$(Get-Date -f 'HH:mm:ss')] $msg" -ForegroundColor Cyan }
function Pass  { param([string]$msg) Write-Host "  [PASS] $msg" -ForegroundColor Green }
function Fail  { param([string]$msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Info  { param([string]$msg) Write-Host "  [INFO] $msg" -ForegroundColor Gray }

$results = @{ Pass = 0; Fail = 0 }

function Check {
    param([bool]$ok, [string]$label, [string]$detail = "")
    if ($ok) { Pass $label; $results.Pass++ }
    else      { Fail "$label — $detail"; $results.Fail++ }
}

# ─────────────────────────────────────────────────────────────────────────────
Log "1. Health Check — GET $ApiUrl/"
# ─────────────────────────────────────────────────────────────────────────────
try {
    $r = Invoke-RestMethod -Uri "$ApiUrl/" -Method GET -TimeoutSec 30
    Check ($r.status -eq "ok") "Health check returns {status: ok}" "Got: $($r | ConvertTo-Json -Compress)"
} catch {
    Check $false "Health check reachable" "Error: $_"
}

# ─────────────────────────────────────────────────────────────────────────────
Log "2. Swagger Docs — GET $ApiUrl/docs"
# ─────────────────────────────────────────────────────────────────────────────
try {
    $r = Invoke-WebRequest -Uri "$ApiUrl/docs" -TimeoutSec 15
    Check ($r.StatusCode -eq 200) "Swagger docs accessible" "HTTP $($r.StatusCode)"
} catch {
    Check $false "Swagger docs accessible" "Error: $_"
}

# ─────────────────────────────────────────────────────────────────────────────
Log "3. SSM Parameter Store — secrets exist"
# ─────────────────────────────────────────────────────────────────────────────
$secretKeys = @("GOOGLE_API_KEY","GROQ_API_KEY","LANGCHAIN_API_KEY","ADZUNA_APP_ID","ADZUNA_APP_KEY")
foreach ($key in $secretKeys) {
    try {
        $p = & $AWS ssm get-parameter --name "/$AppName/$key" --with-decryption --region $Region --query "Parameter.Name" --output text 2>&1
        Check ($LASTEXITCODE -eq 0) "SSM /$AppName/$key exists" "$p"
    } catch {
        Check $false "SSM /$AppName/$key" "$_"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
Log "4. S3 Bucket — accessible"
# ─────────────────────────────────────────────────────────────────────────────
$AccountId = & $AWS sts get-caller-identity --query "Account" --output text
$S3Bucket  = "$AppName-resumes-$AccountId"
try {
    & $AWS s3api head-bucket --bucket $S3Bucket --region $Region 2>&1 | Out-Null
    Check ($LASTEXITCODE -eq 0) "S3 bucket $S3Bucket exists and accessible"
} catch {
    Check $false "S3 bucket accessible" "$_"
}

# ─────────────────────────────────────────────────────────────────────────────
Log "5. ECR — image exists"
# ─────────────────────────────────────────────────────────────────────────────
try {
    $images = & $AWS ecr list-images --repository-name "$AppName-backend" --region $Region --query "imageIds" --output json | ConvertFrom-Json
    Check ($images.Count -gt 0) "ECR image present ($($images.Count) tag(s))"
} catch {
    Check $false "ECR image check" "$_"
}

# ─────────────────────────────────────────────────────────────────────────────
Log "6. ECS Service — RUNNING task"
# ─────────────────────────────────────────────────────────────────────────────
try {
    $svc = & $AWS ecs describe-services `
        --cluster "$AppName-cluster" `
        --services "$AppName-backend" `
        --region $Region `
        --output json | ConvertFrom-Json
    $running = $svc.services[0].runningCount
    $desired = $svc.services[0].desiredCount
    Check ($running -eq $desired -and $running -gt 0) "ECS: $running/$desired tasks running"
} catch {
    Check $false "ECS service check" "$_"
}

# ─────────────────────────────────────────────────────────────────────────────
Log "7. Job Search endpoint — GET $ApiUrl/search-jobs?title=Software+Engineer"
# ─────────────────────────────────────────────────────────────────────────────
try {
    $r = Invoke-RestMethod -Uri "$ApiUrl/search-jobs?title=Software+Engineer&results=3" -Method GET -TimeoutSec 60
    Check ($r.status -eq "success") "Job search returns results" "Count: $($r.count)"
    Info "Sample job: $($r.jobs[0].title) @ $($r.jobs[0].company)"
} catch {
    Check $false "Job search endpoint" "Error: $_"
}

# ─────────────────────────────────────────────────────────────────────────────
Log "8. Resume Upload endpoint — POST $ApiUrl/upload-resume"
# ─────────────────────────────────────────────────────────────────────────────
# Create a tiny valid-enough PDF for testing
$miniPdf = [byte[]]@(
    0x25,0x50,0x44,0x46,0x2D,0x31,0x2E,0x34,0x0A,
    0x31,0x20,0x30,0x20,0x6F,0x62,0x6A,0x0A,0x3C,0x3C,0x2F,0x54,0x79,0x70,0x65,0x20,0x2F,0x43,0x61,0x74,0x61,0x6C,0x6F,0x67,0x2F,0x50,0x61,0x67,0x65,0x73,0x20,0x32,0x20,0x30,0x20,0x52,0x3E,0x3E,0x0A,0x65,0x6E,0x64,0x6F,0x62,0x6A,0x0A,
    0x25,0x25,0x45,0x4F,0x46
)
$tmpPdf = Join-Path $env:TEMP "test_resume.pdf"
[System.IO.File]::WriteAllBytes($tmpPdf, $miniPdf)

try {
    # multipart/form-data upload
    $form = @{ file = Get-Item $tmpPdf }
    $r = Invoke-RestMethod -Uri "$ApiUrl/upload-resume" -Method POST -Form $form -TimeoutSec 60
    # A minimal PDF won't parse successfully but the endpoint should respond
    Check ($null -ne $r) "Upload-resume endpoint reachable" "Response: $($r | ConvertTo-Json -Compress)"
} catch {
    $errMsg = $_.Exception.Message
    # A 500 "Failed to process resume" with a tiny test PDF is expected and acceptable
    $acceptable = $errMsg -match "Failed to process resume" -or $errMsg -match "500"
    Check $acceptable "Upload-resume endpoint reachable (expected parse error on dummy PDF)" "Error: $errMsg"
}

# ─────────────────────────────────────────────────────────────────────────────
Log "9. CloudWatch Logs — log group exists"
# ─────────────────────────────────────────────────────────────────────────────
try {
    $lg = & $AWS logs describe-log-groups `
        --log-group-name-prefix "/ecs/$AppName-backend" `
        --region $Region `
        --query "logGroups[0].logGroupName" `
        --output text
    Check ($lg -and $lg -ne "None") "CloudWatch log group: $lg"
} catch {
    Check $false "CloudWatch log group" "$_"
}

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Test Results: $($results.Pass) passed, $($results.Fail) failed" -ForegroundColor $(if ($results.Fail -eq 0) { "Green" } else { "Red" })
Write-Host "============================================================" -ForegroundColor White
Write-Host ""
if ($results.Fail -eq 0) {
    Write-Host "  All checks passed! Your backend is healthy on AWS." -ForegroundColor Green
    Write-Host "  Set this in Vercel: NEXT_PUBLIC_API_URL=$ApiUrl" -ForegroundColor Cyan
} else {
    Write-Host "  Some checks failed. Check CloudWatch logs:" -ForegroundColor Yellow
    Write-Host "  https://console.aws.amazon.com/cloudwatch/home?region=$Region#logsV2:log-groups/log-group/\$252Fecs\$252F$AppName-backend" -ForegroundColor Yellow
}
