import json
import subprocess
import time
import sys

AWS = r"C:\Program Files\Amazon\AWSCLIV2\aws.exe"
REGION = "ap-south-1"
ACCOUNT_ID = "437672023362"
APP_NAME = "resumematch"
CLUSTER_NAME = "resumematch-cluster"
SERVICE_NAME = "resumematch-backend"

def run_aws(*args):
    cmd = [AWS] + list(args) + ["--region", REGION, "--output", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command {' '.join(cmd)} failed:\n{res.stderr}")
    return json.loads(res.stdout) if res.stdout.strip() else {}

print("[1] Building ECS Task Definition...")
task_def = {
    "family": SERVICE_NAME,
    "networkMode": "awsvpc",
    "requiresCompatibilities": ["FARGATE"],
    "cpu": "1024",
    "memory": "3072",
    "executionRoleArn": f"arn:aws:iam::{ACCOUNT_ID}:role/ecsTaskExecutionRole",
    "taskRoleArn": f"arn:aws:iam::{ACCOUNT_ID}:role/ecsTaskExecutionRole",
    "containerDefinitions": [
        {
            "name": SERVICE_NAME,
            "image": f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/{APP_NAME}-backend:latest",
            "portMappings": [
                {
                    "containerPort": 8000,
                    "protocol": "tcp"
                }
            ],
            "essential": True,
            "environment": [
                {"name": "S3_BUCKET", "value": f"{APP_NAME}-resumes-{ACCOUNT_ID}"},
                {"name": "CHROMA_DB_PATH", "value": "/app/chroma_db"},
                {"name": "ATS_DB_PATH", "value": "/app/ats.db"},
                {"name": "LANGCHAIN_TRACING_V2", "value": "true"},
                {"name": "LANGCHAIN_PROJECT", "value": "resumematch"},
                {"name": "FRONTEND_URL", "value": "*"}
            ],
            "secrets": [
                {"name": "GOOGLE_API_KEY", "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT_ID}:parameter/{APP_NAME}/GOOGLE_API_KEY"},
                {"name": "GOOGLE_API_KEY_2", "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT_ID}:parameter/{APP_NAME}/GOOGLE_API_KEY_2"},
                {"name": "GROQ_API_KEY", "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT_ID}:parameter/{APP_NAME}/GROQ_API_KEY"},
                {"name": "GROQ_API_KEY_2", "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT_ID}:parameter/{APP_NAME}/GROQ_API_KEY_2"},
                {"name": "LANGCHAIN_API_KEY", "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT_ID}:parameter/{APP_NAME}/LANGCHAIN_API_KEY"},
                {"name": "ADZUNA_APP_ID", "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT_ID}:parameter/{APP_NAME}/ADZUNA_APP_ID"},
                {"name": "ADZUNA_APP_KEY", "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT_ID}:parameter/{APP_NAME}/ADZUNA_APP_KEY"}
            ],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": f"/ecs/{SERVICE_NAME}",
                    "awslogs-region": REGION,
                    "awslogs-stream-prefix": "ecs",
                    "awslogs-create-group": "true"
                }
            },
            "healthCheck": {
                "command": [
                    "CMD-SHELL",
                    "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/')\" || exit 1"
                ],
                "interval": 30,
                "timeout": 10,
                "retries": 3,
                "startPeriod": 90
            }
        }
    ]
}

with open("task_def.json", "w", encoding="utf-8") as f:
    json.dump(task_def, f, indent=2)

print("[2] Registering Task Definition...")
reg_res = run_aws("ecs", "register-task-definition", "--cli-input-json", "file://task_def.json")
task_def_arn = reg_res["taskDefinition"]["taskDefinitionArn"]
print(f"  -> Registered: {task_def_arn}")

print("[3] Getting VPC and Subnets...")
vpcs = run_aws("ec2", "describe-vpcs", "--filters", "Name=isDefault,Values=true")
vpc_id = vpcs["Vpcs"][0]["VpcId"]
print(f"  -> Default VPC: {vpc_id}")

subnets = run_aws("ec2", "describe-subnets", "--filters", f"Name=vpc-id,Values={vpc_id}")
subnet_ids = [s["SubnetId"] for s in subnets["Subnets"][:2]]
print(f"  -> Using Subnets: {subnet_ids}")

print("[4] Ensuring Security Group...")
sg_name = f"{APP_NAME}-ecs-sg"
sgs = run_aws("ec2", "describe-security-groups", "--filters", f"Name=group-name,Values={sg_name}", f"Name=vpc-id,Values={vpc_id}")
if sgs["SecurityGroups"]:
    sg_id = sgs["SecurityGroups"][0]["GroupId"]
    print(f"  -> SG already exists: {sg_id}")
else:
    create_sg = run_aws("ec2", "create-security-group", "--group-name", sg_name, "--description", "ResumeMatch ECS Service SG", "--vpc-id", vpc_id)
    sg_id = create_sg["GroupId"]
    print(f"  -> SG created: {sg_id}")
    for port in [8000, 80, 443]:
        try:
            run_aws("ec2", "authorize-security-group-ingress", "--group-id", sg_id, "--protocol", "tcp", "--port", str(port), "--cidr", "0.0.0.0/0")
        except Exception as e:
            print(f"  Ingress port {port}: {e}")

print("[5] Creating / Updating ECS Fargate Service...")
services = run_aws("ecs", "describe-services", "--cluster", CLUSTER_NAME, "--services", SERVICE_NAME)
svc_list = [s for s in services.get("services", []) if s.get("status") != "INACTIVE"]

net_config = {
    "awsvpcConfiguration": {
        "subnets": subnet_ids,
        "securityGroups": [sg_id],
        "assignPublicIp": "ENABLED"
    }
}
with open("net_config.json", "w", encoding="utf-8") as f:
    json.dump(net_config, f)

if svc_list and svc_list[0].get("status") == "ACTIVE":
    print("  -> Service exists, updating with new task definition...")
    run_aws("ecs", "update-service", "--cluster", CLUSTER_NAME, "--service", SERVICE_NAME, "--task-definition", task_def_arn, "--force-new-deployment")
    print("  -> Service updated!")
else:
    print("  -> Creating new ECS Fargate service...")
    cmd = [
        AWS, "ecs", "create-service",
        "--cluster", CLUSTER_NAME,
        "--service-name", SERVICE_NAME,
        "--task-definition", task_def_arn,
        "--desired-count", "1",
        "--launch-type", "FARGATE",
        "--network-configuration", "file://net_config.json",
        "--region", REGION,
        "--output", "json"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to create service:\n{res.stderr}")
    print(f"  -> Service created: {SERVICE_NAME}")

print("\n[6] Waiting for Task to reach RUNNING state...")
public_ip = None
for attempt in range(30):
    time.sleep(10)
    tasks = run_aws("ecs", "list-tasks", "--cluster", CLUSTER_NAME, "--service-name", SERVICE_NAME)
    task_arns = tasks.get("taskArns", [])
    if task_arns:
        desc = run_aws("ecs", "describe-tasks", "--cluster", CLUSTER_NAME, "--tasks", task_arns[0])
        task = desc["tasks"][0]
        status = task.get("lastStatus")
        containers = task.get("containers", [])
        health = containers[0].get("healthStatus", "UNKNOWN") if containers else "UNKNOWN"
        print(f"  Attempt {attempt+1}/30: Task Status = {status}, Health = {health}")
        
        if status == "RUNNING":
            for attachment in task.get("attachments", []):
                for detail in attachment.get("details", []):
                    if detail.get("name") == "networkInterfaceId":
                        eni_id = detail["value"]
                        eni_info = run_aws("ec2", "describe-network-interfaces", "--network-interface-ids", eni_id)
                        assoc = eni_info["NetworkInterfaces"][0].get("Association", {})
                        public_ip = assoc.get("PublicIp")
                        break
            if public_ip:
                print(f"\n============================================================")
                print(f"  SUCCESS! Task is RUNNING!")
                print(f"  Public IP: {public_ip}")
                print(f"  API URL:   http://{public_ip}:8000")
                print(f"  Health:    http://{public_ip}:8000/")
                print(f"  Docs:      http://{public_ip}:8000/docs")
                print(f"============================================================")
                break
    else:
        print(f"  Attempt {attempt+1}/30: Waiting for task to be scheduled...")

if not public_ip:
    print("Task took longer than expected to start. Check AWS Console / CloudWatch.")
