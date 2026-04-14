# budget-flask — Infrastructure Reference

**Last updated:** 2026-04-10
**Owner:** APAC Marketing (Terence)
**Public URL:** https://budget.pepperstone-asia.live
**AWS account:** `292828418386`
**Region:** `ap-southeast-1` (Singapore)

This document is the single source of truth for every cloud resource backing the app. Keep it current whenever you change infra.

---

## 1. Architecture at a glance

```
         Internet
            │  HTTPS (443)
            ▼
   ┌──────────────────────┐
   │  ALB (public)        │   ACM cert: budget.pepperstone-asia.live
   │  budget-flask-alb    │   SG: budget-flask-alb-sg
   └──────────┬───────────┘
              │  HTTP 8000 (VPC-internal)
              ▼
   ┌──────────────────────┐
   │  ECS Fargate Service │   Cluster: budget-flask
   │  budget-flask        │   Task def: budget-flask:4
   │  Image: ECR          │   SG: budget-flask-sg
   └──────┬───────────┬───┘
          │           │
          │           │ psycopg2 / 5432
          │           ▼
          │   ┌────────────────────┐
          │   │  RDS Postgres 16.13│   budget-flask-db
          │   │  db.t4g.micro      │   SG: budget-flask-rds-sg
          │   └────────────────────┘
          │
          ▼ (outbound HTTPS)
   ┌──────────────────────┐        ┌──────────────────────┐
   │  Google Sheets API   │        │  BigQuery            │
   │  (legacy / fallback) │        │  PM spend data       │
   └──────────────────────┘        └──────────────────────┘
```

Mode switch: `USE_POSTGRES=true` (current prod) routes all reads/writes to RDS. Set to `false` to fall back to Google Sheets without a rebuild.

---

## 2. Networking

### 2.1 VPC
| Attribute | Value |
|-----------|-------|
| VPC ID | `vpc-0a6950f10a36e0985` |
| Name | default VPC |
| CIDR | `172.31.0.0/16` |

### 2.2 Subnets (all currently public — see Security Audit AWS-M-1)
| ID | AZ | CIDR | Type |
|----|----|------|------|
| `subnet-08f21a88b291787d1` | ap-southeast-1a | 172.31.32.0/20 | public |
| `subnet-0147123a0aabff873` | ap-southeast-1b | 172.31.16.0/20 | public |
| `subnet-0e75c571c955181f1` | ap-southeast-1c | 172.31.0.0/20  | public |

### 2.3 Security groups

#### `budget-flask-alb-sg` — `sg-04614cb2b032bf761`
| Direction | Proto | Port | Source/Dest |
|-----------|-------|------|-------------|
| Inbound   | TCP   | 443  | 0.0.0.0/0 (internet) |
| Outbound  | ALL   | ALL  | 0.0.0.0/0 |

#### `budget-flask-sg` (ECS task) — `sg-07b9c3b0e39754ffb`
| Direction | Proto | Port | Source/Dest |
|-----------|-------|------|-------------|
| Inbound   | TCP   | 8000 | `sg-04614cb2b032bf761` (ALB SG) |
| Outbound  | ALL   | ALL  | 0.0.0.0/0 (needs internet for BigQuery, Google Sheets, ECR, Secrets Manager) |

#### `budget-flask-rds-sg` — `sg-019b667144477846a`
| Direction | Proto | Port | Source/Dest |
|-----------|-------|------|-------------|
| Inbound   | TCP   | 5432 | `sg-07b9c3b0e39754ffb` (ECS task SG) |
| Outbound  | ALL   | ALL  | 0.0.0.0/0 *(should be tightened)* |

---

## 3. DNS & TLS

| Attribute | Value |
|-----------|-------|
| Hostname | `budget.pepperstone-asia.live` |
| DNS target | `budget-flask-alb-1849750806.ap-southeast-1.elb.amazonaws.com` |
| Hosted zone | **Not in this AWS account** — managed externally (verify where the `pepperstone-asia.live` zone lives; the CNAME → ALB is maintained there) |
| ACM certificate | `arn:aws:acm:ap-southeast-1:292828418386:certificate/25e1b6d8-7bca-4005-91eb-80ba2ee1167b` |
| Cert status | ISSUED, expires **2026-10-23**, auto-renewal ELIGIBLE |
| Cert SANs | `budget.pepperstone-asia.live` |

---

## 4. Load balancer

| Attribute | Value |
|-----------|-------|
| Name | `budget-flask-alb` |
| ARN | `arn:aws:elasticloadbalancing:ap-southeast-1:292828418386:loadbalancer/app/budget-flask-alb/639543dabdd7d0ca` |
| Scheme | internet-facing |
| VPC | `vpc-0a6950f10a36e0985` |
| Security group | `sg-04614cb2b032bf761` |
| DNS | `budget-flask-alb-1849750806.ap-southeast-1.elb.amazonaws.com` |

### 4.1 Listener
| Port | Protocol | SSL policy | Default action |
|------|----------|-----------|----------------|
| 443  | HTTPS    | `ELBSecurityPolicy-2016-08` *(outdated — upgrade to `ELBSecurityPolicy-TLS13-1-2-2021-06`)* | forward → `budget-flask-tg` |

There is **no HTTP (port 80) listener**. Plain HTTP attempts drop at the SG.

### 4.2 Target group
| Attribute | Value |
|-----------|-------|
| Name | `budget-flask-tg` |
| ARN | `arn:aws:elasticloadbalancing:ap-southeast-1:292828418386:targetgroup/budget-flask-tg/1e70ff390c2fb025` |
| Protocol / Port | HTTP / 8000 |
| Target type | ip (Fargate awsvpc) |
| VPC | `vpc-0a6950f10a36e0985` |
| Health check | `GET /` on traffic-port, interval 30s, timeout 5s, healthy=2, unhealthy=2 |

---

## 5. ECS

### 5.1 Cluster
| Attribute | Value |
|-----------|-------|
| Name | `budget-flask` |
| Launch type | Fargate |
| Capacity providers | (default, none explicitly set) |

### 5.2 Service — `budget-flask`
| Attribute | Value |
|-----------|-------|
| Launch type | FARGATE |
| Platform version | LATEST |
| Desired count | 1 *(single instance — see AWS-M-2)* |
| Task definition | `budget-flask:4` |
| Health check grace | 60s |
| Subnets | `subnet-08f21a88b291787d1` only *(single AZ — needs all 3)* |
| Security groups | `sg-07b9c3b0e39754ffb` |
| Assign public IP | ENABLED *(should be DISABLED with private subnets + NAT)* |
| Load balancer | `budget-flask-tg`, container `budget-flask:8000` |

### 5.3 Task definition — `budget-flask` (active revision: 4)
| Attribute | Value |
|-----------|-------|
| Family | `budget-flask` |
| Network mode | awsvpc |
| Requires | FARGATE |
| CPU / Memory | 512 / 1024 MiB |
| Execution role | `arn:aws:iam::292828418386:role/ecsTaskExecutionRole` |
| Task role | `arn:aws:iam::292828418386:role/budget-flask-task-role` *(no policies attached; safe to remove)* |
| Container name | `budget-flask` |
| Image | `292828418386.dkr.ecr.ap-southeast-1.amazonaws.com/budget-flask:latest` |
| Port mapping | `8000/tcp` |
| Log driver | `awslogs` → `/ecs/budget-flask` |

**Environment variables:**
| Name | Value |
|------|-------|
| `SHEET_ID` | `13TMeZ3pqdUQr2WRMG5G70xchZKfmiPVOShZChqbUsv4` |
| `BQ_PROJECT_ID` | `gen-lang-client-0602500310` |
| `BQ_DATASET` | `pepperstone_apac` |
| `BQ_TABLE` | `ad_performance` |
| `BQ_LOCATION` | `asia-southeast1` |
| `USE_POSTGRES` | `true` |

**Secrets (injected from Secrets Manager by execution role):**
| Name | Secret ARN |
|------|-----------|
| `SECRET_KEY` | `.../budget-app/secret-key-6cZpPD` |
| `GOOGLE_CREDS_JSON` | `.../budget-app/google-credentials-t4jwbf` |
| `DATABASE_URL` | `.../budget-flask/database-url-FdC73X` |

**Revision history:**
- `:1`, `:2`, `:3` — pre-PostgreSQL (Google Sheets only)
- `:4` — active — adds `USE_POSTGRES=true` and `DATABASE_URL` secret (deployed 2026-04-10)

---

## 6. Container registry

| Attribute | Value |
|-----------|-------|
| Repository | `budget-flask` |
| URI | `292828418386.dkr.ecr.ap-southeast-1.amazonaws.com/budget-flask` |
| Encryption | AES256 (AWS managed) |
| Tag mutability | **MUTABLE** *(should be IMMUTABLE)* |
| Scan on push | **false** *(should be true)* |
| Current tags | `latest`, `postgres` (same digest: `sha256:4f76859e191cb351bda6697166d64de64151c9423518f2da3fd5a2e300727d4b`) |

Build + push sequence:
```bash
aws ecr get-login-password --region ap-southeast-1 | \
  docker login --username AWS --password-stdin 292828418386.dkr.ecr.ap-southeast-1.amazonaws.com

docker buildx build --platform linux/amd64 \
  -t 292828418386.dkr.ecr.ap-southeast-1.amazonaws.com/budget-flask:latest \
  --load .

docker push 292828418386.dkr.ecr.ap-southeast-1.amazonaws.com/budget-flask:latest
```

Deploy (after push):
```bash
aws ecs register-task-definition --cli-input-json file://ecs/task-definition.json --region ap-southeast-1
aws ecs update-service --cluster budget-flask --service budget-flask \
  --task-definition budget-flask --force-new-deployment --region ap-southeast-1
```

---

## 7. Database — RDS

| Attribute | Value |
|-----------|-------|
| Identifier | `budget-flask-db` |
| Engine | PostgreSQL 16.13 |
| Instance class | `db.t4g.micro` (2 vCPU, 1 GiB RAM) |
| Storage | 20 GiB gp3 |
| Multi-AZ | false |
| Publicly accessible | false |
| Storage encrypted | **false** *(HIGH — remediate via snapshot+restore)* |
| KMS key | — |
| IAM DB auth | disabled |
| Backup retention | 7 days |
| Auto minor upgrade | true |
| Deletion protection | **false** *(HIGH — enable)* |
| CloudWatch log exports | none |
| Performance Insights | disabled |
| VPC | `vpc-0a6950f10a36e0985` |
| Security group | `sg-019b667144477846a` |
| Subnet group | `budget-flask-db-subnet` (all 3 AZs) |
| Endpoint | `budget-flask-db.cpa64u6aswjt.ap-southeast-1.rds.amazonaws.com:5432` |
| Database name | `budget_flask` |
| Master username | `budget_admin` |
| Master password | stored only in Secrets Manager `budget-flask/database-url` |

### 7.1 Schema
Defined in `schema.sql` (8 tables): `budgets`, `channels`, `activities`, `entries`, `channel_mapping`, `vendors`, `users`, `categories`.

**Current row counts (as migrated 2026-04-10):** 13 budgets, 127 channels, 270 activities, 252 entries, 19 mappings, 79 vendors, 9 users, 51 categories.

### 7.2 Migration / re-seed
Read from Google Sheets source of truth and upsert into RDS. Requires temporary public access (see SOP below) or an in-VPC runner.

```bash
DATABASE_URL='postgresql://budget_admin:<pwd>@<endpoint>:5432/budget_flask' \
SHEET_ID='13TMeZ3pqdUQr2WRMG5G70xchZKfmiPVOShZChqbUsv4' \
python3 migrate_data.py
```

---

## 8. Secrets Manager

| Name | ARN suffix | Used by | Last changed | Rotation |
|------|-----------|---------|-------------|---------|
| `budget-app/secret-key` | `-6cZpPD` | Flask session signing | 2026-04-08 | **none** |
| `budget-app/google-credentials` | `-t4jwbf` | Google service account JSON (Sheets + BigQuery) | 2026-04-08 | **none** |
| `budget-flask/database-url` | `-FdC73X` | RDS connection string | 2026-04-10 | **none** |

All three use the default AWS-managed KMS key.

**IAM access:** `ecsTaskExecutionRole` has inline policy `budget-flask-secrets-access` allowing `secretsmanager:GetSecretValue` on `budget-app/*` and `budget-flask/*`.

---

## 9. IAM

### 9.1 `ecsTaskExecutionRole`
- Trust: `ecs-tasks.amazonaws.com`
- Managed: `AmazonECSTaskExecutionRolePolicy`
- Inline `budget-flask-secrets-access`:
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": [
        "arn:aws:secretsmanager:ap-southeast-1:292828418386:secret:budget-app/*",
        "arn:aws:secretsmanager:ap-southeast-1:292828418386:secret:budget-flask/*"
      ]
    }]
  }
  ```

### 9.2 `budget-flask-task-role`
- Trust: `ecs-tasks.amazonaws.com`
- **No policies attached.** Referenced by the task definition but currently unused. Safe to remove from `task-definition.json` (container will still work).

---

## 10. Logging & monitoring

| Resource | Value |
|----------|-------|
| Log group | `/ecs/budget-flask` |
| Retention | **infinite (null)** *(should be 90d)* |
| KMS | none |
| Current size | ~1.2 MB |
| Log streams | `ecs/budget-flask/<task-id>` per running task |

No CloudWatch alarms, no dashboards, no SNS topics, no CloudTrail trail local to this project. RDS Enhanced Monitoring and Performance Insights are both OFF.

---

## 11. External dependencies

| Service | Purpose | Credential |
|---------|---------|-----------|
| Google Sheets API | Legacy read/write (fallback when `USE_POSTGRES=false`); also the source of truth mirrored into RDS via `migrate_data.py` | `GOOGLE_CREDS_JSON` secret |
| Google Drive API | Required alongside Sheets for gspread | same |
| BigQuery | Source of PM ad spend data consumed by `api_pm.py` | same Google service account |

Spreadsheet ID: `13TMeZ3pqdUQr2WRMG5G70xchZKfmiPVOShZChqbUsv4`
BigQuery table: `gen-lang-client-0602500310.pepperstone_apac.ad_performance` (loc `asia-southeast1`)

---

## 12. Standard operating procedures

### 12.1 Deploy a new version
```bash
# 1. Build & push
cd /path/to/budget-flask
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 292828418386.dkr.ecr.ap-southeast-1.amazonaws.com
docker buildx build --platform linux/amd64 -t 292828418386.dkr.ecr.ap-southeast-1.amazonaws.com/budget-flask:latest --load .
docker push 292828418386.dkr.ecr.ap-southeast-1.amazonaws.com/budget-flask:latest

# 2. Register task def + roll
aws ecs register-task-definition --cli-input-json file://ecs/task-definition.json --region ap-southeast-1
aws ecs update-service --cluster budget-flask --service budget-flask --force-new-deployment --region ap-southeast-1

# 3. Watch
aws ecs describe-services --cluster budget-flask --services budget-flask \
  --query 'services[0].deployments[0].rolloutState' --region ap-southeast-1
```

### 12.2 Rollback
```bash
# Point service at previous task definition revision
aws ecs update-service --cluster budget-flask --service budget-flask \
  --task-definition budget-flask:3 --force-new-deployment --region ap-southeast-1
```
Revision 3 is the last Google-Sheets-only build. Revision 4 is PostgreSQL-enabled.

### 12.3 Toggle off PostgreSQL (emergency)
Edit task definition, set `USE_POSTGRES=false`, register, roll. App falls back to Google Sheets within one deploy.

### 12.4 Run `schema.sql` / `migrate_data.py` against RDS
RDS lives in a private network. Temporary workflow:
```bash
# 1. Add your public IP to the RDS SG
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id sg-019b667144477846a \
  --protocol tcp --port 5432 --cidr ${MY_IP}/32 --region ap-southeast-1
# 2. Enable public access
aws rds modify-db-instance --db-instance-identifier budget-flask-db \
  --publicly-accessible --apply-immediately --region ap-southeast-1
# ... wait until "available" ...
# 3. Run scripts
DATABASE_URL='postgresql://...' python3 -c "import psycopg2,os; c=psycopg2.connect(os.environ['DATABASE_URL']); c.autocommit=True; c.cursor().execute(open('schema.sql').read())"
DATABASE_URL='postgresql://...' SHEET_ID='13TMeZ3pqdUQr2WRMG5G70xchZKfmiPVOShZChqbUsv4' python3 migrate_data.py
# 4. REVERT
aws rds modify-db-instance --db-instance-identifier budget-flask-db \
  --no-publicly-accessible --apply-immediately --region ap-southeast-1
aws ec2 revoke-security-group-ingress --group-id sg-019b667144477846a \
  --security-group-rule-ids <sgr-id-from-step-1> --region ap-southeast-1
```

### 12.5 Rotate a Secrets Manager secret
```bash
aws secretsmanager update-secret --secret-id <name> --secret-string '<new-value>' --region ap-southeast-1
aws ecs update-service --cluster budget-flask --service budget-flask --force-new-deployment --region ap-southeast-1
```
`--force-new-deployment` is required because ECS only injects secrets at container start.

### 12.6 Snapshot RDS
```bash
aws rds create-db-snapshot \
  --db-instance-identifier budget-flask-db \
  --db-snapshot-identifier budget-flask-db-$(date +%Y%m%d) \
  --region ap-southeast-1
```

---

## 13. Resource inventory (quick reference)

| Kind | Name | ID / ARN |
|------|------|---------|
| VPC | default | `vpc-0a6950f10a36e0985` |
| Subnets | 1a / 1b / 1c | `subnet-08f21a88b291787d1` / `subnet-0147123a0aabff873` / `subnet-0e75c571c955181f1` |
| SG (ALB) | `budget-flask-alb-sg` | `sg-04614cb2b032bf761` |
| SG (ECS) | `budget-flask-sg` | `sg-07b9c3b0e39754ffb` |
| SG (RDS) | `budget-flask-rds-sg` | `sg-019b667144477846a` |
| ALB | `budget-flask-alb` | `.../loadbalancer/app/budget-flask-alb/639543dabdd7d0ca` |
| TG | `budget-flask-tg` | `.../targetgroup/budget-flask-tg/1e70ff390c2fb025` |
| ACM cert | `budget.pepperstone-asia.live` | `.../certificate/25e1b6d8-7bca-4005-91eb-80ba2ee1167b` |
| ECS cluster | `budget-flask` | — |
| ECS service | `budget-flask` | — |
| Task def | `budget-flask:4` | `.../task-definition/budget-flask:4` |
| ECR repo | `budget-flask` | `292828418386.dkr.ecr.ap-southeast-1.amazonaws.com/budget-flask` |
| RDS | `budget-flask-db` | endpoint `budget-flask-db.cpa64u6aswjt.ap-southeast-1.rds.amazonaws.com` |
| DB subnet group | `budget-flask-db-subnet` | — |
| Secret | `budget-app/secret-key` | `.../budget-app/secret-key-6cZpPD` |
| Secret | `budget-app/google-credentials` | `.../budget-app/google-credentials-t4jwbf` |
| Secret | `budget-flask/database-url` | `.../budget-flask/database-url-FdC73X` |
| IAM role | `ecsTaskExecutionRole` | — |
| IAM role | `budget-flask-task-role` | — |
| CW log group | `/ecs/budget-flask` | — |

---

## 14. Open action items (see `SECURITY_AUDIT.md` for full list)

1. Enable RDS deletion protection **(1 min)**
2. Upgrade ALB SSL policy to `ELBSecurityPolicy-TLS13-1-2-2021-06` **(1 min)**
3. ECR `scanOnPush=true`, `IMMUTABLE`, move deploys off `:latest` **(1 h)**
4. Multi-AZ ECS service: all 3 subnets, `desiredCount≥2` **(15 min)**
5. CloudWatch log retention → 90 days **(1 min)**
6. RDS encryption via snapshot → encrypted restore → cutover **(2 h + cutover)**
7. Rotate all user default passwords and remove from source **(1 h)**
8. Add CSRF + session cookie hardening + login rate limit **(~4 h total)**
9. Fix activity endpoint authorization **(30 min)**
10. Define secret rotation SOP **(1 h)**
