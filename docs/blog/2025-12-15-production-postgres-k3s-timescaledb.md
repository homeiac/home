# Deploying Production-Class PostgreSQL on K3s: TimescaleDB, pgvector, and Automated Cloud Backups

*How I deployed a fully-featured PostgreSQL database with time-series, vector embeddings, and geospatial capabilities on a homelab K3s cluster, complete with automated backups to Google Drive.*

---

## The Challenge

I needed a PostgreSQL database for my homelab that could handle:

- **Time-series data** from IoT sensors and monitoring
- **Vector embeddings** for AI/ML workloads (RAG, semantic search)
- **Geospatial queries** for location-based data
- **Automated backups** with cloud redundancy
- **GitOps deployment** for reproducibility

Most tutorials stop at "deploy PostgreSQL." Real production systems need backup strategies, disaster recovery plans, and proper secret management. This is the full story.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        K3s Cluster                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   database namespace                      │    │
│  │  ┌─────────────────┐  ┌─────────────────┐               │    │
│  │  │   PostgreSQL    │  │  Backup CronJob │               │    │
│  │  │  + TimescaleDB  │  │   (2 AM daily)  │               │    │
│  │  │  + pgvector     │  └────────┬────────┘               │    │
│  │  │  + PostGIS      │           │                        │    │
│  │  └────────┬────────┘           ▼                        │    │
│  │           │           ┌─────────────────┐               │    │
│  │           ▼           │  postgres-backup │               │    │
│  │  ┌─────────────────┐  │      PVC        │               │    │
│  │  │  postgres-data  │  └────────┬────────┘               │    │
│  │  │      PVC        │           │                        │    │
│  │  │    (100Gi)      │           ▼                        │    │
│  │  └─────────────────┘  ┌─────────────────┐               │    │
│  │                       │ GDrive CronJob  │               │    │
│  │                       │  (3 AM daily)   │               │    │
│  └───────────────────────┴────────┬────────┴───────────────┘    │
│                                   │                              │
└───────────────────────────────────┼──────────────────────────────┘
                                    │
                                    ▼
                          ┌─────────────────┐
                          │  Google Drive   │
                          │ (Cloud Backup)  │
                          └─────────────────┘
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Database | PostgreSQL 16 | Core RDBMS |
| Time-series | TimescaleDB 2.24 | Hypertables, continuous aggregates |
| Vector DB | pgvector 0.8.1 | Embeddings, similarity search |
| Geospatial | PostGIS 3.6.1 | Geographic data, spatial queries |
| Helm Chart | Bitnami PostgreSQL | Kubernetes deployment |
| GitOps | Flux CD | Declarative infrastructure |
| Secrets | SOPS + age | Encrypted secrets in git |
| Backup | rclone | Cloud sync to Google Drive |

## Step 1: The Helm Release

Using Bitnami's PostgreSQL chart with a custom TimescaleDB image:

```yaml
# gitops/clusters/homelab/apps/postgres/helmrelease.yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: postgres
  namespace: database
spec:
  interval: 30m
  chart:
    spec:
      chart: postgresql
      version: "16.4.1"
      sourceRef:
        kind: HelmRepository
        name: bitnami
        namespace: flux-system
  values:
    image:
      registry: docker.io
      repository: timescale/timescaledb-ha
      tag: pg16-all  # Includes TimescaleDB + pgvector + PostGIS

    auth:
      existingSecret: postgres-credentials
      secretKeys:
        adminPasswordKey: postgres-password

    primary:
      persistence:
        enabled: true
        size: 100Gi

      # Enable extensions on startup
      initdb:
        scripts:
          init-extensions.sql: |
            CREATE EXTENSION IF NOT EXISTS timescaledb;
            CREATE EXTENSION IF NOT EXISTS vector;
            CREATE EXTENSION IF NOT EXISTS postgis;
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
            CREATE EXTENSION IF NOT EXISTS btree_gin;
            CREATE EXTENSION IF NOT EXISTS btree_gist;

      resources:
        requests:
          memory: 1Gi
          cpu: 500m
        limits:
          memory: 4Gi
          cpu: 2000m
```

**Key decisions:**

1. **TimescaleDB-HA image** - Includes all extensions pre-built (no compile-from-source pain)
2. **100Gi storage** - Room for time-series data growth
3. **Init scripts** - Extensions created automatically on first boot
4. **Resource limits** - Prevent runaway queries from killing the node

## Step 2: SOPS-Encrypted Secrets

Never commit plaintext credentials. Using Mozilla SOPS with age encryption:

```yaml
# gitops/clusters/homelab/apps/postgres/secret.yaml (encrypted)
apiVersion: v1
kind: Secret
metadata:
  name: postgres-credentials
  namespace: database
stringData:
  postgres-password: ENC[AES256_GCM,data:Vht4J8gP7lDM...,type:str]
sops:
  age:
    - recipient: age1uwvq3llqjt666t4ckls9wv44wcpxxwlu8svqwx5kc7v76hncj94qg3tsna
```

Flux automatically decrypts at deploy time. The actual password never appears in git history.

**Setup:**
```bash
# Generate age key
age-keygen -o ~/.config/sops/age/keys.txt

# Create Flux decryption secret
kubectl create secret generic sops-age \
  --namespace=flux-system \
  --from-file=age.agekey=~/.config/sops/age/keys.txt

# Encrypt secrets
sops --encrypt --in-place secret.yaml
```

## Step 3: Automated Backup Strategy

### Tier 1: Daily pg_dumpall (2 AM)

```yaml
# gitops/clusters/homelab/apps/postgres/backup-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: database
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: bitnami/postgresql:16
            command:
            - /bin/bash
            - -c
            - |
              BACKUP_FILE="/backup/pg_dumpall_$(date +%Y%m%d_%H%M%S).sql.gz"
              PGPASSWORD="$POSTGRES_PASSWORD" pg_dumpall \
                -h postgres-postgresql \
                -U postgres | gzip > "$BACKUP_FILE"

              # Retention: keep last 7 days
              find /backup -name "pg_dumpall_*.sql.gz" -mtime +7 -delete

              echo "Backup complete: $BACKUP_FILE"
              ls -lh /backup/
            volumeMounts:
            - name: backup
              mountPath: /backup
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: postgres-backup
```

### Tier 2: Cloud Sync to Google Drive (3 AM)

```yaml
# gitops/clusters/homelab/apps/postgres/gdrive-sync-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-gdrive-sync
  namespace: database
spec:
  schedule: "0 3 * * *"  # 3 AM (after backup completes)
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: sync
            image: rclone/rclone:latest
            command:
            - /bin/sh
            - -c
            - |
              rclone sync /backup/ gdrive-backup:homelab-backup/postgres/ \
                --config /config/rclone/rclone.conf \
                -v
            volumeMounts:
            - name: backup
              mountPath: /backup
              readOnly: true
            - name: rclone-config
              mountPath: /config/rclone
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: postgres-backup
          - name: rclone-config
            secret:
              secretName: rclone-gdrive-config  # SOPS encrypted
```

**Why two tiers?**

1. **Local backup (2 AM)** - Fast recovery for "oops I dropped a table"
2. **Cloud sync (3 AM)** - Survives complete cluster loss

## Step 4: Testing the Restore

A backup is worthless if you can't restore from it. Here's the test script:

```bash
#!/bin/bash
# test-postgres-restore.sh --from-gdrive

# Download latest backup from Google Drive
rclone copy gdrive-backup:homelab-backup/postgres/ /tmp/restore/ \
  --include "pg_dumpall_*.sql.gz"

# Get latest file
BACKUP=$(ls -t /tmp/restore/*.gz | head -1)
gunzip -k "$BACKUP"

# Create test database and restore
kubectl exec -n database postgres-postgresql-0 -- \
  psql -U postgres -c "CREATE DATABASE restore_test;"

kubectl cp "${BACKUP%.gz}" database/postgres-postgresql-0:/tmp/restore.sql
kubectl exec -n database postgres-postgresql-0 -- \
  psql -U postgres -d restore_test -f /tmp/restore.sql

# Verify
kubectl exec -n database postgres-postgresql-0 -- \
  psql -U postgres -d restore_test -c "\dt"

# Cleanup
kubectl exec -n database postgres-postgresql-0 -- \
  psql -U postgres -c "DROP DATABASE restore_test;"
```

**Test results:**
```
=========================================
PostgreSQL Restore Test
=========================================

Downloading latest backup from Google Drive...
Latest backup: pg_dumpall_20251215_192723.sql.gz
Backup file: 2.7K (compressed) / 13K (uncompressed)

Creating test database: restore_test_5034
CREATE DATABASE

Restoring to test database...
SET
ALTER ROLE
...

Verifying Restore:
Databases: postgres, restore_test_5034, template0, template1
Extensions: plpgsql (restored successfully)

Cleanup:
DROP DATABASE

The restore test was successful!
```

## Database Size Analysis

```sql
SELECT pg_database.datname,
       pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database
ORDER BY pg_database_size(pg_database.datname) DESC;
```

| Database | Size |
|----------|------|
| postgres | 18 MB |
| template1 | 7.5 MB |
| template0 | 7.3 MB |

The 18MB base size comes from the extensions:
- TimescaleDB 2.24.0
- pgvector 0.8.1
- PostGIS 3.6.1
- uuid-ossp, pg_trgm, btree_gin, btree_gist

The backup is only 2.7KB compressed because `pg_dumpall` outputs SQL commands, not binary data. Extensions are installed by the container image, data comes from the backup.

## The Complete Backup Schedule

| Time | Component | Method | RPO |
|------|-----------|--------|-----|
| 2:00 AM | PostgreSQL dump | K8s CronJob | 24h |
| 2:30 AM | VM/LXC backups | Proxmox Backup Server | 24h |
| 3:00 AM | GDrive sync | K8s CronJob | 24h |
| 10:30 PM | VM/LXC backups | Proxmox Backup Server | 12h |

**Disaster recovery scenarios:**

1. **Dropped table** → Restore from local PVC backup (minutes)
2. **Pod corruption** → Helm release recreates it (minutes)
3. **Node failure** → PBS restores VM, Flux redeploys (1-2 hours)
4. **Site disaster** → GDrive backup + GitOps repo (hours)

## Lessons Learned

### 1. Use the Right Image

Don't try to install TimescaleDB into the vanilla PostgreSQL image. The `timescale/timescaledb-ha` image has everything pre-compiled and tested together.

### 2. Init Scripts for Extensions

Extensions must be created after the database starts. Using Helm's `initdb.scripts` ensures they're created on first boot, not on every restart.

### 3. Separate Backup PVC

Don't backup to the same PVC as your data. A separate `postgres-backup` PVC means:
- Backups survive data PVC corruption
- Can mount read-only in sync job
- Clear separation of concerns

### 4. Test Your Restores

I wrote `test-postgres-restore.sh` that runs monthly. A backup you haven't tested is not a backup.

### 5. SOPS for Everything

Every secret (database password, rclone OAuth token) is SOPS-encrypted. The age private key is backed up to two Proxmox hosts. Lose the key = lose access to all secrets.

## Files Created

```
gitops/clusters/homelab/apps/postgres/
├── namespace.yaml
├── helmrepository.yaml
├── helmrelease.yaml
├── secret.yaml              # SOPS encrypted
├── rclone-secret.yaml       # SOPS encrypted
├── backup-cronjob.yaml
├── gdrive-sync-cronjob.yaml
├── ingressroutetcp.yaml
└── kustomization.yaml

scripts/backup/
├── install-rclone.sh
├── setup-rclone-gdrive.sh
├── sync-postgres-to-gdrive.sh
├── test-backup-strategy.sh
└── test-postgres-restore.sh
```

## Conclusion

Production-class database deployment isn't just about getting PostgreSQL running. It's about:

- **Extensions** that match your workload (time-series, vectors, geo)
- **Secrets** that never touch git history
- **Backups** that run automatically
- **Cloud sync** for disaster recovery
- **Tested restores** that prove it all works

The entire setup is GitOps-managed. If my cluster burns down tomorrow, I clone the repo, bootstrap Flux, and everything comes back - including the database with data from Google Drive.

Total time from "I need a database" to "production-ready with cloud backups": about 4 hours. Most of that was debugging the TimescaleDB image tag.

---

*This deployment is part of my AI-managed homelab infrastructure. The entire setup was planned and implemented with Claude Code, following Infrastructure as Code principles.*

**Repository:** [github.com/homeiac/home](https://github.com/homeiac/home)
