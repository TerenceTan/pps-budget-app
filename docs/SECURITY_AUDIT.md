# Security Audit — budget-flask

**Audit date:** 2026-04-10
**Scope:** Application code (`app.py`, `auth.py`, `api_pm.py`, `config.py`, `db.py`, `sheets_helper.py`, `schema.sql`, `Dockerfile`) and AWS infrastructure (ECS, ALB, RDS, Secrets Manager, ECR, IAM, VPC/SG, CloudWatch).

Severity key: **CRITICAL** → fix immediately · **HIGH** → fix this week · **MEDIUM** → fix this sprint · **LOW** → backlog.

---

## 1. Executive summary

The app is functional and has reasonable baseline protections (authenticated routes, parameterized SQL, HTTPS, private-ish RDS), but several items materially raise risk for a tool that handles marketing budgets and vendor invoices:

- **Credentials & identity:** default passwords hardcoded in source, no CSRF protection, no failed-login rate limiting, no password policy.
- **AuthZ gaps:** activity CRUD endpoints are open to any logged-in user regardless of country; some authorization checks use a different, weaker heuristic than `check_country_access`.
- **Data at rest:** RDS is **not encrypted**, there is no deletion protection, and the ALB is on an outdated TLS policy that still allows TLS 1.0/1.1.
- **Operational:** single-AZ single-task deployment, ECS task running in a public subnet with a public IP, ECR `latest` tag is mutable, CloudWatch logs retained forever, no secret rotation.

None of the findings indicate active compromise. Most can be remediated in a few hours; the RDS-encryption item requires a snapshot/restore cycle.

---

## 2. Application code findings

### 2.1 CRITICAL / HIGH

#### H-1  Hardcoded default user passwords in source (`config.py:53-63`)
```python
DEFAULT_USERS = [
    ("pepper", "APAC@123", ...),
    ("affiliate", "Affiliate@123", ...),
    ...
]
```
These are seeded on first startup when the users table is empty. They are also committed to git history, so anyone with repo read access knows the initial passwords for all roles, including the `pepper` admin.
**Fix:** Remove defaults from source. Seed a single admin with a password generated at deploy time (read from Secrets Manager or a one-shot env var), then force a password change on first login. For existing users, rotate all 9 passwords now and treat `APAC@123` et al. as compromised.

> **Resolved 2026-04-10:** `DEFAULT_USERS` removed from source (`config.py`). `auth.seed_users()` rewritten to bootstrap a single admin via `BOOTSTRAP_ADMIN_PASSWORD` env var. All 9 accounts re-rotated with 16-char random passwords (pbkdf2:sha256). New plaintexts stored in AWS Secrets Manager at `budget-flask/user-passwords`. Old plaintexts (`APAC@123` etc.) remain in git history at commits `0ffe4b0` and `b0452f7` and are considered permanently compromised; history intentionally not rewritten because rotated values make the exposure moot.

#### H-2  No CSRF protection on any state-changing endpoint
Every `POST`/`PUT`/`DELETE` in `app.py` and `api_pm.py` relies solely on the session cookie. No CSRF token is checked. A logged-in admin visiting an attacker page can be made to delete users, channels, entries, or trigger PM sync.
**Fix:** Add `flask-wtf` CSRFProtect, or implement a double-submit cookie pattern. Since all write endpoints are JSON/form, a lightweight `X-CSRF-Token` header check against a session-bound token is sufficient.

#### H-3  Activity endpoints lack authorization checks (`app.py:207-245`)
```python
@app.route("/api/activities", methods=["POST"])
@require_login
def api_add_activity(): ...
```
`api_add_activity`, `api_update_activity`, `api_delete_activity` are protected only by `@require_login`. Any country user can create, rename, or delete activities in any other country.
**Fix:** Add `check_country_access(d["country"])` (for create) and a country check on the loaded record (for update/delete). Consider also requiring `require_admin` for delete.

#### H-4  No brute-force protection on login (`app.py:60-70`)
`/login` has no rate limiting, lockout, or captcha. Combined with H-1 (known default passwords) this is trivially brute-forceable from the internet.
**Fix:** Add `flask-limiter` with a strict per-IP+username budget (e.g. 5/minute, 20/hour) and lock the account for N minutes after M failures. Log all failed attempts.

#### H-5  Default `SECRET_KEY` fallback (`config.py:5`)
```python
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
```
Production currently injects `SECRET_KEY` from Secrets Manager, so this fallback is not active — but a single deployment slip (missing env, renamed secret) would silently drop the app onto a hard-coded key and every existing session cookie would become forgeable.
**Fix:** `raise RuntimeError` if `SECRET_KEY` is missing. Never ship a fallback.

### 2.2 MEDIUM

#### M-1  Inconsistent country-access enforcement (`app.py:310-320, 488-498`)
`api_delete_entry`, `api_export`, `api_export_xlsx` gate access by comparing to `session["user"]` (which is set to the *first* market when a country user has multiple markets, see `app.py:69`). A country user with `markets="ID,IN,MY"` will have `session["user"] = "ID"` and therefore can't delete/export `IN` or `MY` data even though they should, and conversely can't be reasoned about uniformly.
**Fix:** Always use `check_country_access(country)` for country gating. Remove the `session["user"]` shortcut.

#### M-2  No session cookie hardening
`app.py` never sets `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, or `PERMANENT_SESSION_LIFETIME`.
**Fix:**
```python
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
```

#### M-3  Error messages leak internals
Many routes return `jsonify({"error": str(e)}), 500`, so psycopg2/gspread/BigQuery errors (including table names, column names, partial SQL) are returned to the browser.
**Fix:** Log the exception with `app.logger.exception(...)`, return a generic message to the client (`"Internal error"`).

#### M-4  `db.py` uses an f-string column name in `get_filtered` (`db.py:74`)
```python
conditions.append(f"{k} = %s")
```
Values are parameterized, but the **column name** comes from the caller's `**filters` dict. Today all callers pass hardcoded keys (`country=`, `quarter=`, `channel_id=`), so there's no live SQLi — but a future refactor that threads user input into `**filters` would open one. Defense-in-depth fix: whitelist allowed columns per table.

#### M-5  `save_invoice_to_disk` has no size or content-type limit (`app.py:38-45`)
A malicious admin or compromised session can POST unbounded base64 payloads; each entry POST writes N files to the container's ephemeral disk.
**Fix:** Enforce a max invoice size (e.g. 5 MB), validate MIME type against an allowlist (`pdf`, `png`, `jpeg`), and count invoices per entry.

#### M-6  Invoices stored on ephemeral container disk (`app.py:34`)
`INVOICE_DIR` is inside the container. On every Fargate task restart/deploy, previously uploaded invoice files are lost. Base64 fallback (older entries) still works because `invoice_data` in the DB holds the data URL, but any invoice saved via the disk path is gone after a deploy.
**Fix:** Move invoice storage to S3 (budget-flask-invoices bucket with bucket-owner-enforced, SSE-KMS, blocked public access). Store only the S3 key in the DB.

#### M-7  No password policy on user create (`app.py:355-367`)
`api_add_user` accepts any non-empty password.
**Fix:** Enforce min 12 chars, mix of classes, reject top-N common passwords.

#### M-8  No transactions — `db.py` uses autocommit
`get_connection()` sets `autocommit=True`, so multi-step sync operations (create channel → create activity → insert entry) can partially apply under error. Specifically affects `api_pm.auto_sync` when channel/activity creation succeeds but entry insert fails.
**Fix:** Add a `with_transaction()` context manager; wrap auto_sync per-row.

#### M-9  Dockerfile runs as root
No `USER` directive. If an RCE is found, the attacker starts as root inside the container.
**Fix:**
```dockerfile
RUN useradd -m -u 10001 app
USER app
```

### 2.3 LOW

- **L-1  Login page enumerates all usernames** via a dropdown populated from `get_all_users()`. Minor info disclosure. (`app.py:55`, `templates/login.html`)
- **L-2  No audit logging** of logins, admin actions, or entry deletes. Only gunicorn access logs exist.
- **L-3  Unused files** `sheets.py` and `apply_pm_fix.py` appear to be legacy; remove to reduce confusion and attack surface.
- **L-4  `docker-compose.yml` has local-only `POSTGRES_PASSWORD: localdev123`** — acceptable for local dev but add a comment so nobody lifts it into prod.
- **L-5  `requirements.txt` is unpinned for transitive deps.** Consider `pip-compile` → `requirements.lock`.

---

## 3. AWS infrastructure findings

### 3.1 CRITICAL / HIGH

#### AWS-H-1  RDS storage is NOT encrypted at rest
```
StorageEncrypted: false
KmsKeyId: null
```
`budget-flask-db` stores plaintext marketing spend, vendor names, invoice metadata, and bcrypt hashes. **RDS encryption cannot be enabled in place.**
**Fix procedure:**
1. Snapshot current DB: `aws rds create-db-snapshot --db-instance-identifier budget-flask-db --db-snapshot-identifier budget-flask-db-pre-encrypt`
2. Copy snapshot with encryption: `aws rds copy-db-snapshot --source-db-snapshot-identifier budget-flask-db-pre-encrypt --target-db-snapshot-identifier budget-flask-db-encrypted --kms-key-id alias/aws/rds`
3. Restore from encrypted snapshot as `budget-flask-db-new`.
4. Cut over: update Secrets Manager DATABASE_URL to new endpoint, redeploy ECS.
5. Delete old instance after verification.

#### AWS-H-2  RDS deletion protection disabled
One `aws rds delete-db-instance` away from data loss.
**Fix:** `aws rds modify-db-instance --db-instance-identifier budget-flask-db --deletion-protection --apply-immediately --region ap-southeast-1`

#### AWS-H-3  ALB TLS policy is outdated
```
SslPolicy: ELBSecurityPolicy-2016-08
```
This policy still permits TLS 1.0/1.1 and a handful of weak ciphers.
**Fix:**
```
aws elbv2 modify-listener \
  --listener-arn <HTTPS-listener-ARN> \
  --ssl-policy ELBSecurityPolicy-TLS13-1-2-2021-06 \
  --region ap-southeast-1
```

#### AWS-H-4  ECR `scanOnPush: false` and `MUTABLE` tags
- No CVE scan is triggered on image push, so we deploy without knowing what vulnerabilities ride along.
- Tag mutability `MUTABLE` lets anyone overwrite `:latest` — rollback becomes guesswork.
**Fix:**
```
aws ecr put-image-scanning-configuration --repository-name budget-flask --image-scanning-configuration scanOnPush=true --region ap-southeast-1
aws ecr put-image-tag-mutability --repository-name budget-flask --image-tag-mutability IMMUTABLE --region ap-southeast-1
```
Then switch deploy process to use git-SHA tags (not `:latest`).

#### AWS-H-5  No rotation on any secret
- `budget-app/secret-key` — Flask session signing key
- `budget-app/google-credentials` — Google service account JSON (full-access to sheet + BigQuery read)
- `budget-flask/database-url` — RDS master credentials
All three show `LastRotatedDate: null`.
**Fix:** Document a manual rotation SOP (once/quarter) at minimum. For database-url, Secrets Manager can automate rotation with a Lambda if we later add it.

### 3.2 MEDIUM

#### AWS-M-1  ECS tasks in public subnets with public IPs
`assignPublicIp: ENABLED` in a subnet where `MapPublicIpOnLaunch: true`. The task only opens port 8000 to the ALB SG, so exposure is limited — but every restart reveals a new public IPv4 that accepts SYN on 8000 from the internet (connection resets, but still enumerable).
**Fix:** Create private subnets + NAT gateway (or VPC endpoints for ECR/Secrets/CloudWatch/S3), move the service into them, set `assignPublicIp=DISABLED`.

#### AWS-M-2  Service runs in a single subnet / single AZ
`subnets: [subnet-08f21a88b291787d1]` (only `ap-southeast-1a`), `desiredCount: 1`. AZ outage = full app outage.
**Fix:** Update service to list all 3 subnets; set desiredCount ≥ 2 so at least two AZs are always live.

#### AWS-M-3  RDS single-AZ
`MultiAZ: false`. AZ outage = DB outage. Acceptable for an internal tool but document the RTO.
**Fix (optional):** `aws rds modify-db-instance --db-instance-identifier budget-flask-db --multi-az --apply-immediately`

#### AWS-M-4  No CloudWatch log exports from RDS
`EnabledCloudwatchLogsExports: null`. Postgres errors, slow queries, and connection logs are not exported, so we lose diagnostics + audit.
**Fix:** Enable `postgresql` log export and set a parameter group to log `log_statement=ddl`, `log_min_duration_statement=1000`.

#### AWS-M-5  CloudWatch log group `/ecs/budget-flask` has no retention
`retentionInDays: null` — logs accumulate forever.
**Fix:** `aws logs put-retention-policy --log-group-name /ecs/budget-flask --retention-in-days 90 --region ap-southeast-1`

#### AWS-M-6  No AWS WAF on the ALB
Public ALB has no managed rule set. A public-facing Flask app benefits from the AWS Managed Core Rule Set at minimum.
**Fix:** Create a WAFv2 WebACL with `AWSManagedRulesCommonRuleSet` and `AWSManagedRulesKnownBadInputsRuleSet`; associate with the ALB.

#### AWS-M-7  RDS SG egress is 0.0.0.0/0 all-ports
RDS has no reason to make outbound connections.
**Fix:** Replace default egress with a deny-all (or drop egress rule entirely — SG egress can be empty in VPCs).

### 3.3 LOW

- **AWS-L-1  Secrets encrypted with default AWS-managed KMS key** — acceptable, but customer-managed key gives per-secret key policy + rotation logging.
- **AWS-L-2  `budget-flask-task-role` has no policies attached.** Either remove the role from the task definition (use only `ecsTaskExecutionRole`), or give it the least-privilege permissions it actually needs.
- **AWS-L-3  RDS master username `budget_admin`** — not a secret but easily guessed; not exploitable given network isolation.
- **AWS-L-4  Secret naming inconsistent**: `budget-app/*` vs `budget-flask/*`. Pick one prefix.
- **AWS-L-5  Default VPC** — infra lives in the account's default VPC. Long-term, move to a dedicated VPC for the app.

---

## 4. Prioritized remediation checklist

| # | Item | Severity | Effort |
|---|------|----------|--------|
| 1 | Rotate all 9 default user passwords and remove them from source | HIGH | 1h |
| 2 | Enable RDS deletion protection | HIGH | 1m |
| 3 | Upgrade ALB SSL policy to `ELBSecurityPolicy-TLS13-1-2-2021-06` | HIGH | 1m |
| 4 | Enable ECR `scanOnPush`, set `IMMUTABLE` tags, move deploys off `:latest` | HIGH | 1h |
| 5 | Add `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` + remove SECRET_KEY fallback | HIGH | 30m |
| 6 | Add CSRF protection (flask-wtf or header token) | HIGH | 2h |
| 7 | Fix activity endpoint authorization (add `check_country_access`) | HIGH | 30m |
| 8 | Add flask-limiter on `/login` | HIGH | 30m |
| 9 | Snapshot → encrypted restore → cutover for RDS encryption | HIGH | 2h + cutover |
| 10 | Set CloudWatch log retention to 90 days | MEDIUM | 1m |
| 11 | Multi-AZ ECS service (all 3 subnets, desiredCount=2) | MEDIUM | 15m |
| 12 | Enable RDS postgres log export + param group | MEDIUM | 30m |
| 13 | Non-root Dockerfile user | MEDIUM | 15m |
| 14 | Consolidate country-access checks (remove `session["user"]` shortcut) | MEDIUM | 1h |
| 15 | Stop returning `str(e)` to clients | MEDIUM | 1h |
| 16 | Move invoices to S3 | MEDIUM | half day |
| 17 | WAF WebACL on ALB | MEDIUM | 30m |
| 18 | Private subnets + NAT for ECS | MEDIUM | half day |
| 19 | Define secret rotation SOP | MEDIUM | 1h |
| 20 | Delete legacy `sheets.py`, `apply_pm_fix.py` | LOW | 10m |

---

## 5. Verification commands

```bash
# RDS encryption
aws rds describe-db-instances --db-instance-identifier budget-flask-db \
  --query 'DBInstances[0].{enc:StorageEncrypted,del:DeletionProtection}' --region ap-southeast-1

# ALB TLS policy
aws elbv2 describe-listeners --load-balancer-arn <ALB-ARN> \
  --query 'Listeners[0].SslPolicy' --region ap-southeast-1

# ECR config
aws ecr describe-repositories --repository-names budget-flask \
  --query 'repositories[0].{scan:imageScanningConfiguration,mutability:imageTagMutability}' \
  --region ap-southeast-1

# CloudWatch retention
aws logs describe-log-groups --log-group-name-prefix /ecs/budget-flask \
  --query 'logGroups[0].retentionInDays' --region ap-southeast-1
```
