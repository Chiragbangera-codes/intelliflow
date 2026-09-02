# IntelliFlow AI — Database Backup & Disaster Recovery Runbook

**System:** PostgreSQL 16 (Relational Store) + FAISS (Vector Index) + Storage (Uploaded Documents)  
**Retention Policy:** 30-day automated rolling window  
**Target RPO (Recovery Point Objective):** < 1 hour (with hourly cron)  
**Target RTO (Recovery Time Objective):** < 15 minutes  

---

## 1. Backup Strategy Overview

A comprehensive backup of IntelliFlow AI comprises three synchronized layers:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          INTELLIFLOW BACKUP ARCHIVE                    │
├─────────────────────────┬────────────────────────┬─────────────────────┤
│   PostgreSQL 16 DB      │    FAISS Vector Store  │  Uploaded Documents │
│  (Tables, Migrations,   │   (Document Embeddings │  (PDF, DOCX, Images │
│   Users, RBAC, Outbox)  │    & Chunk Indexes)    │   Stored on Disk)   │
│   → .sql.gz (pg_dump)   │    → index.faiss       │   → storage/ archive│
└─────────────────────────┴────────────────────────┴─────────────────────┘
```

---

## 2. Automated PostgreSQL Backup

### Script Location
- Bash: `scripts/backup_database.sh`
- PowerShell: `scripts/backup_database.ps1`

### Execution Details
- Uses native PostgreSQL `pg_dump` with `--clean --if-exists` flags.
- Directly streams output through `gzip` for compression.
- Generates ISO timestamped filenames: `backups/intelliflow_YYYY-MM-DD_HHMMSS.sql.gz`.
- Performs post-backup verification:
  1. Checks file presence and minimum byte size (> 100 bytes).
  2. Tests archive stream integrity (`gzip --test`).
  3. Verifies non-empty SQL statement stream.
- Automatically prunes backups older than the retention threshold (default: 30 days).

### Manual Backup Command
```bash
./scripts/backup_database.sh /opt/intelliflow/backups 30
```

### Automated Cron Schedule
To execute backups daily at 02:00 AM UTC, add to crontab (`crontab -e`):

```cron
0 2 * * * /opt/intelliflow/scripts/backup_database.sh /opt/intelliflow/backups 30 >> /var/log/intelliflow_backup.log 2>&1
```

---

## 3. Database Restoration Procedure

### ⚠️ Pre-Restoration Critical Safety Rule
The restoration script automatically captures a **pre-restore safety backup** (`pre_restore_safety_YYYY-MM-DD_HHMMSS.sql.gz`) before executing destructive changes.

### Script Location
- Bash: `scripts/restore_database.sh`
- PowerShell: `scripts/restore_database.ps1`

### Interactive Restoration
```bash
./scripts/restore_database.sh /opt/intelliflow/backups/intelliflow_2026-09-02_195901.sql.gz
```
*Prompts for explicit confirmation keyword `RESTORE`.*

### Non-Interactive Restoration (Automated Recovery)
```bash
./scripts/restore_database.sh /opt/intelliflow/backups/intelliflow_2026-09-02_195901.sql.gz --confirm
```

### Post-Restoration Validation
The script automatically executes:
1. Database connectivity check.
2. Alembic migration verification (`alembic current` vs `alembic heads`).
3. Application readiness probe.

---

## 4. Disaster Recovery Drill Record

**Drill Date:** 2026-09-02 19:59 UTC  
**Environment:** Live Docker Containerized PostgreSQL 16  
**Operator:** Automated Test Suite / QA Subagent  

### Execution Steps & Verified Outcomes:

| Step | Action | Expected Result | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **1** | Insert test data record (`BACKUP_DRILL_MARKER`) | Record stored in `settings` table | Record stored (count: 1) | ✅ PASS |
| **2** | Execute `pg_dump` with gzip compression | Archive generated and validated | `77,830` bytes archive created | ✅ PASS |
| **3** | Test archive integrity (`gzip --test`) | Zero compression errors | PASS | ✅ PASS |
| **4** | Delete test marker (`DELETE FROM settings`) | Record removed from DB | Count: 0 | ✅ PASS |
| **5** | Restore database from created archive | Full schema & rows restored | Restore completed (exit code 0) | ✅ PASS |
| **6** | Query test marker | Record restored to original state | Count: 1 (`present_before_backup`) | ✅ PASS |
| **7** | Verify Alembic migration state | Schema matches `007` (HEAD) | `007_integrations_event_bus (head)` | ✅ PASS |

**Drill Verdict: 100% RECOVERY SUCCESS**
