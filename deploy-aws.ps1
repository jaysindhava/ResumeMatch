#!/usr/bin/env pwsh
# =============================================================================
# deploy-aws.ps1  —  Full AWS deployment script for ResumeMatch backend
#
# Usage:
#   .\deploy-aws.ps1 -AccountId "123456789012" -Region "ap-south-1"
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker Desktop running
#   - Secrets already in .env file
# =============================================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$AccountId,

    [string]$Region      = "ap-south-1",
    [string]$AppName     = "resumematch",
    [string]$ClusterName = "resumematch-cluster",
    [string]$ServiceName = "resumematch-backend"
)

$AWS = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$ECR_URI = "$AccountId.dkr.ecr.$Region.amazonaws.com/$AppName-backend"

# ─────────────────────────────────────────────────────────────────────────────
function Log { param([string]$msg) Write-Host "`n[$(Get-Date -f 'HH:mm:ss')] $msg" -ForegroundColor Cyan }
function Ok  { param([string]$msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Err { param([string]$msg) Write-Host "  ✗ $msg" -ForegroundColor Red; exit 1 }

# ─────────────────────────────────────────────────────────────────────────────
# STEP 0 — Verify prerequisites
# ─────────────────────────────────────────────────────────────────────────────
Log "Verifying prerequisites..."

& $AWS sts get-caller-identity --output text 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Err "AWS credentials not configured. Run 'aws configure' first." }
Ok "AWS credentials OK"

docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Err "Docker is not running. Start Docker Desktop first." }
Ok "Docker OK"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Read secrets from .env
# ─────────────────────────────────────────────────────────────────────────────
Log "Reading secrets from .env..."
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { Err ".env file not found at $envFile" }

$envVars = @{}
Get-Content $envFile | Where-Object { $_ -match "^[^#].*=.*" } | ForEach-Object {
    $parts = $_ -split "=", 2
    if ($parts.Count -eq 2) {
        $key   = $parts[0].Trim()
        $value = $parts[1].Trim()
        $envVars[$key] = $value
    }
}
Ok "Loaded $($envVars.Count) env vars"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Create ECR repository
# ─────────────────────────────────────────────────────────────────────────────
Log "Creating ECR repository..."
$repoCheck = & $AWS ecr describe-repositories --repository-names "$AppName-backend" --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    & $AWS ecr create-repository `
        --repository-name "$AppName-backend" `
        --region $Region `
        --image-scanning-configuration scanOnPush=true `
        --output json | Out-Null
    Ok "ECR repository created: $AppName-backend"
} else {
    Ok "ECR repository already exists"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Store secrets in SSM Parameter Store
# ─────────────────────────────────────────────────────────────────────────────
Log "Storing secrets in SSM Parameter Store..."
$secretKeys = @("GOOGLE_API_KEY","GOOGLE_API_KEY_2","GROQ_API_KEY","GROQ_API_KEY_2",
                "LANGCHAIN_API_KEY","ADZUNA_APP_ID","ADZUNA_APP_KEY")
foreach ($key in $secretKeys) {
    if ($envVars.ContainsKey($key)) {
        & $AWS ssm put-parameter `
            --name "/$AppName/$key" `
            --value $envVars[$key] `
            --type SecureString `
            --overwrite `
            --region $Region `
            --output json | Out-Null
        Ok "SSM: /$AppName/$key"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Create S3 bucket for resume uploads
# ─────────────────────────────────────────────────────────────────────────────
Log "Creating S3 bucket..."
$S3Bucket = "$AppName-resumes-$AccountId"
$bucketCheck = & $AWS s3api head-bucket --bucket $S3Bucket --region $Region 2>&1
if ($LASTEXITCODE -ne 0) {
    & $AWS s3api create-bucket `
        --bucket $S3Bucket `
        --region $Region `
        --create-bucket-configuration LocationConstraint=$Region `
        --output json | Out-Null

    # Block all public access
    & $AWS s3api put-public-access-block `
        --bucket $S3Bucket `
        --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" `
        --region $Region | Out-Null
    Ok "S3 bucket created: $S3Bucket"
} else {
    Ok "S3 bucket already exists"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Build & push Docker image to ECR
# ─────────────────────────────────────────────────────────────────────────────
Log "Building Docker image (this takes a few minutes for first build)..."
docker build -t "$AppName-backend" .
if ($LASTEXITCODE -ne 0) { Err "Docker build failed" }
Ok "Docker image built"

Log "Authenticating Docker with ECR..."
& $AWS ecr get-login-password --region $Region | `
    docker login --username AWS --password-stdin "$AccountId.dkr.ecr.$Region.amazonaws.com"
if ($LASTEXITCODE -ne 0) { Err "ECR login failed" }
Ok "ECR login OK"

Log "Tagging & pushing image to ECR..."
docker tag "$AppName-backend:latest" "$ECR_URI:latest"
docker push "$ECR_URI:latest"
if ($LASTEXITCODE -ne 0) { Err "Docker push failed" }
Ok "Image pushed to ECR: $ECR_URI:latest"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Create ECS Cluster
# ─────────────────────────────────────────────────────────────────────────────
Log "Creating ECS cluster..."
$clusterCheck = & $AWS ecs describe-clusters --clusters $ClusterName --region $Region --query "clusters[0].status" --output text 2>&1
if ($clusterCheck -ne "ACTIVE") {
    & $AWS ecs create-cluster --cluster-name $ClusterName --region $Region --output json | Out-Null
    Ok "ECS cluster created: $ClusterName"
} else {
    Ok "ECS cluster already exists"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Ensure IAM role for ECS tasks
# ─────────────────────────────────────────────────────────────────────────────
Log "Setting up ECS task IAM role..."
$roleName = "ecsTaskExecutionRole"
$roleCheck = & $AWS iam get-role --role-name $roleName 2>&1
if ($LASTEXITCODE -ne 0) {
    $trustPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    & $AWS iam create-role --role-name $roleName --assume-role-policy-document $trustPolicy --output json | Out-Null
    & $AWS iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" | Out-Null
    Ok "IAM role created: $roleName"
} else {
    Ok "IAM role already exists"
}
$roleArn = "arn:aws:iam::${AccountId}:role/$roleName"

# Add SSM read permission to the task execution role
$ssmPolicyDoc = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameters", "ssm:GetParameter", "ssm:GetParametersByPath"],
      "Resource": "arn:aws:ssm:${Region}:${AccountId}:parameter/${AppName}/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject","s3:GetObject","s3:DeleteObject","s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${S3Bucket}", "arn:aws:s3:::${S3Bucket}/*"]
    }
  ]
}
"@
$ssmPolicyName = "resumematch-task-policy"
& $AWS iam put-role-policy --role-name $roleName --policy-name $ssmPolicyName --policy-document $ssmPolicyDoc 2>&1 | Out-Null
Ok "IAM inline policy for SSM + S3 attached"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Register ECS Task Definition
# ─────────────────────────────────────────────────────────────────────────────
Log "Registering ECS task definition..."

# Build secrets array for SSM parameters
$secretsList = @()
foreach ($key in $secretKeys) {
    if ($envVars.ContainsKey($key)) {
        $secretsList += @{
            name      = $key
            valueFrom = "arn:aws:ssm:${Region}:${AccountId}:parameter/${AppName}/$key"
        }
    }
}

$envList = @(
    @{ name = "S3_BUCKET";        value = $S3Bucket },
    @{ name = "CHROMA_DB_PATH";   value = "/mnt/efs/chroma_db" },
    @{ name = "ATS_DB_PATH";      value = "/mnt/efs/ats.db" },
    @{ name = "LANGCHAIN_TRACING_V2"; value = "true" },
    @{ name = "LANGCHAIN_PROJECT"; value = "resumematch" }
)

# Add FRONTEND_URL if known
$frontendUrl = Read-Host "Enter your Vercel frontend URL (e.g. https://resumematch.vercel.app) — press Enter to skip"
if ($frontendUrl) {
    $envList += @{ name = "FRONTEND_URL"; value = $frontendUrl }
}

$taskDef = @{
    family                   = $ServiceName
    networkMode              = "awsvpc"
    requiresCompatibilities  = @("FARGATE")
    cpu                      = "1024"
    memory                   = "3072"
    executionRoleArn         = $roleArn
    taskRoleArn              = $roleArn
    volumes                  = @()     # EFS volume added separately below
    containerDefinitions     = @(@{
        name         = $ServiceName
        image        = "${ECR_URI}:latest"
        portMappings = @(@{ containerPort = 8000; protocol = "tcp" })
        environment  = $envList
        secrets      = $secretsList
        logConfiguration = @{
            logDriver = "awslogs"
            options   = @{
                "awslogs-group"         = "/ecs/$ServiceName"
                "awslogs-region"        = $Region
                "awslogs-stream-prefix" = "ecs"
                "awslogs-create-group"  = "true"
            }
        }
        healthCheck = @{
            command     = @("CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/')\" || exit 1")
            interval    = 30
            timeout     = 10
            retries     = 3
            startPeriod = 90
        }
    })
}

$taskDefJson = $taskDef | ConvertTo-Json -Depth 10
$taskDefFile = Join-Path $env:TEMP "resumematch-task-def.json"
$taskDefJson | Set-Content -Path $taskDefFile -Encoding UTF8

$registerResult = & $AWS ecs register-task-definition `
    --cli-input-json "file://$taskDefFile" `
    --region $Region `
    --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { Err "Task definition registration failed" }
$taskDefArn = $registerResult.taskDefinition.taskDefinitionArn
Ok "Task definition registered: $taskDefArn"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 9 — Get default VPC / subnets / security group
# ─────────────────────────────────────────────────────────────────────────────
Log "Getting VPC/subnet/security group..."
$vpcId = & $AWS ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $Region
$subnets = & $AWS ec2 describe-subnets --filters "Name=vpc-id,Values=$vpcId" --query "Subnets[*].SubnetId" --output text --region $Region
$subnetList = ($subnets -split "\s+")[0..1] -join ","   # use first 2 subnets

# Create security group for the ECS service
$sgName = "$AppName-ecs-sg"
$sgId = & $AWS ec2 describe-security-groups --filters "Name=group-name,Values=$sgName" "Name=vpc-id,Values=$vpcId" --query "SecurityGroups[0].GroupId" --output text --region $Region
if ($sgId -eq "None" -or -not $sgId) {
    $sgId = & $AWS ec2 create-security-group `
        --group-name $sgName `
        --description "ResumeMatch ECS Service SG" `
        --vpc-id $vpcId `
        --query "GroupId" `
        --output text `
        --region $Region
    & $AWS ec2 authorize-security-group-ingress `
        --group-id $sgId `
        --protocol tcp --port 8000 --cidr 0.0.0.0/0 `
        --region $Region | Out-Null
    & $AWS ec2 authorize-security-group-ingress `
        --group-id $sgId `
        --protocol tcp --port 80 --cidr 0.0.0.0/0 `
        --region $Region | Out-Null
    & $AWS ec2 authorize-security-group-ingress `
        --group-id $sgId `
        --protocol tcp --port 443 --cidr 0.0.0.0/0 `
        --region $Region | Out-Null
    Ok "Security group created: $sgId"
} else {
    Ok "Security group already exists: $sgId"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 10 — Create or update ECS Service (without ALB for first test)
# ─────────────────────────────────────────────────────────────────────────────
Log "Creating ECS Fargate service..."
$svcCheck = & $AWS ecs describe-services --cluster $ClusterName --services $ServiceName --region $Region --query "services[0].status" --output text 2>&1
if ($svcCheck -eq "ACTIVE") {
    Log "Service exists — forcing new deployment..."
    & $AWS ecs update-service `
        --cluster $ClusterName `
        --service $ServiceName `
        --task-definition $taskDefArn `
        --force-new-deployment `
        --region $Region `
        --output json | Out-Null
    Ok "Service updated with new image"
} else {
    & $AWS ecs create-service `
        --cluster $ClusterName `
        --service-name $ServiceName `
        --task-definition $taskDefArn `
        --desired-count 1 `
        --launch-type FARGATE `
        --network-configuration "awsvpcConfiguration={subnets=[$subnetList],securityGroups=[$sgId],assignPublicIp=ENABLED}" `
        --region $Region `
        --output json | Out-Null
    if ($LASTEXITCODE -ne 0) { Err "ECS service creation failed" }
    Ok "ECS service created: $ServiceName"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 11 — Wait for service to stabilize and get public IP
# ─────────────────────────────────────────────────────────────────────────────
Log "Waiting for task to reach RUNNING state (up to 3 min)..."
$attempts = 0
$taskPublicIp = $null
while ($attempts -lt 18) {
    Start-Sleep -Seconds 10
    $taskArns = & $AWS ecs list-tasks --cluster $ClusterName --service-name $ServiceName --query "taskArns[0]" --output text --region $Region 2>&1
    if ($taskArns -and $taskArns -ne "None") {
        $taskDetail = & $AWS ecs describe-tasks --cluster $ClusterName --tasks $taskArns --region $Region --output json | ConvertFrom-Json
        $taskStatus = $taskDetail.tasks[0].lastStatus
        Write-Host "  Task status: $taskStatus" -ForegroundColor Yellow
        if ($taskStatus -eq "RUNNING") {
            $eniId = $taskDetail.tasks[0].attachments[0].details | Where-Object { $_.name -eq "networkInterfaceId" } | Select-Object -ExpandProperty value
            $taskPublicIp = & $AWS ec2 describe-network-interfaces --network-interface-ids $eniId --query "NetworkInterfaces[0].Association.PublicIp" --output text --region $Region
            break
        }
    }
    $attempts++
}

# ─────────────────────────────────────────────────────────────────────────────
# DONE — Print summary
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  ResumeMatch Backend Deployed!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
if ($taskPublicIp) {
    Write-Host "  API URL: http://$taskPublicIp:8000" -ForegroundColor Yellow
    Write-Host "  Health:  http://$taskPublicIp:8000/" -ForegroundColor Yellow
    Write-Host "  Docs:    http://$taskPublicIp:8000/docs" -ForegroundColor Yellow
} else {
    Write-Host "  Task not yet running. Check:" -ForegroundColor Yellow
    Write-Host "  aws ecs describe-services --cluster $ClusterName --services $ServiceName --region $Region" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  ECR Image:   $ECR_URI:latest"
Write-Host "  S3 Bucket:   $S3Bucket"
Write-Host "  ECS Cluster: $ClusterName"
Write-Host ""
Write-Host "  Next: Set NEXT_PUBLIC_API_URL=http://$taskPublicIp:8000 in Vercel" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
