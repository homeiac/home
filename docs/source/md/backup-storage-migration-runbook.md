# Backup Storage Migration Runbook

## Overview

This runbook provides step-by-step instructions for migrating Proxmox backup jobs from one storage backend to another, such as migrating from local storage to Proxmox Backup Server (PBS) or between different PBS instances.

## Prerequisites

### Required Access
- Root access to Proxmox cluster nodes
- Access to source and target backup storage
- Sufficient space on target storage for existing backups

### Required Tools
- `pvesh` command (Proxmox CLI)
- `jq` for JSON processing
- Migration script: `/scripts/migrate_backup_storage.sh`

### Pre-Migration Checklist

- [ ] Verify target storage is configured and active
- [ ] Check available space on target storage
- [ ] Identify all backup jobs using source storage
- [ ] Plan migration window (backup jobs should be paused)
- [ ] Create backup of current job configurations
- [ ] Test migration script in dry-run mode

## Migration Scenarios

### Scenario 1: Local to PBS Migration

**Use Case**: Moving from local Proxmox storage to centralized PBS

**Example**: Migrating from `local` storage to `homelab-backup` PBS datastore

```bash
# 1. Check current backup jobs
pvesh get /cluster/backup --output-format json

# 2. Verify target PBS storage
pvesm status | grep homelab-backup

# 3. Dry run migration
./scripts/migrate_backup_storage.sh \
  --from local \
  --to homelab-backup \
  --all \
  --dry-run

# 4. Perform actual migration
./scripts/migrate_backup_storage.sh \
  --from local \
  --to homelab-backup \
  --all
```

### Scenario 2: PBS to PBS Migration

**Use Case**: Upgrading to new PBS instance or changing datastore

**Example**: Migrating from old PBS to new PBS with larger storage

```bash
# 1. Configure new PBS storage in Proxmox
pvesm add pbs homelab-backup-new \
  --server new-pbs.maas \
  --datastore new-datastore \
  --username root@pam

# 2. Test connectivity
pvesm status homelab-backup-new

# 3. Migrate backup jobs
./scripts/migrate_backup_storage.sh \
  --from homelab-backup \
  --to homelab-backup-new \
  --all
```

### Scenario 3: Single Job Migration

**Use Case**: Moving specific backup job for testing or isolation

```bash
# 1. Identify specific job ID
pvesh get /cluster/backup

# 2. Migrate single job
./scripts/migrate_backup_storage.sh \
  --from old-storage \
  --to new-storage \
  --job backup-12345678
```

## Step-by-Step Migration Process

### Phase 1: Preparation

#### 1.1 Storage Verification

```bash
# List all configured storage
pvesm status

# Check target storage details
pvesh get /storage/TARGET_STORAGE

# Verify available space
pvesm status | grep TARGET_STORAGE
```

#### 1.2 Backup Job Analysis

```bash
# List all backup jobs
pvesh get /cluster/backup --output-format json | jq '.'

# Find jobs using source storage
pvesh get /cluster/backup --output-format json | \
  jq '.[] | select(.storage == "SOURCE_STORAGE")'

# Count affected jobs
pvesh get /cluster/backup --output-format json | \
  jq '[.[] | select(.storage == "SOURCE_STORAGE")] | length'
```

#### 1.3 Configuration Backup

```bash
# Export current backup job configurations
mkdir -p /tmp/backup-migration-$(date +%Y%m%d)
pvesh get /cluster/backup --output-format json > \
  /tmp/backup-migration-$(date +%Y%m%d)/backup-jobs-before.json
```

### Phase 2: Migration Execution

#### 2.1 Disable Backup Jobs (Optional)

For critical environments, temporarily disable backup jobs during migration:

```bash
# List jobs to disable
JOBS=$(pvesh get /cluster/backup --output-format json | \
  jq -r '.[] | select(.storage == "SOURCE_STORAGE") | .id')

# Disable each job
for job in $JOBS; do
  pvesh set /cluster/backup/$job --enabled 0
  echo "Disabled job: $job"
done
```

#### 2.2 Run Migration Script

```bash
# Execute migration with logging
./scripts/migrate_backup_storage.sh \
  --from SOURCE_STORAGE \
  --to TARGET_STORAGE \
  --all 2>&1 | tee /tmp/migration-$(date +%Y%m%d_%H%M%S).log
```

#### 2.3 Re-enable Backup Jobs

```bash
# Re-enable migrated jobs
for job in $JOBS; do
  pvesh set /cluster/backup/$job --enabled 1
  echo "Enabled job: $job"
done
```

### Phase 3: Verification

#### 3.1 Configuration Verification

```bash
# Export post-migration configurations
pvesh get /cluster/backup --output-format json > \
  /tmp/backup-migration-$(date +%Y%m%d)/backup-jobs-after.json

# Verify all jobs now use target storage
pvesh get /cluster/backup --output-format json | \
  jq '.[] | select(.storage == "TARGET_STORAGE") | {id, storage}'

# Check for any jobs still using source storage
pvesh get /cluster/backup --output-format json | \
  jq '.[] | select(.storage == "SOURCE_STORAGE")'
```

#### 3.2 Test Backup Execution

```bash
# Run test backup on migrated job
TEST_JOB=$(pvesh get /cluster/backup --output-format json | \
  jq -r '.[] | select(.storage == "TARGET_STORAGE") | .id | first')

# Check if job exists and get VM list
pvesh get /cluster/backup/$TEST_JOB

# Run manual backup test (replace VMID with actual ID)
vzdump VMID --storage TARGET_STORAGE --mode snapshot
```

#### 3.3 Storage Usage Monitoring

```bash
# Monitor target storage usage
watch 'pvesm status | grep TARGET_STORAGE'

# Check backup completion
tail -f /var/log/vzdump.log
```

## Rollback Procedures

### Quick Rollback

If migration fails or issues are detected:

```bash
# 1. Restore from backup configuration
# (Assuming you saved original configs)

# 2. Update jobs back to source storage
for job in $JOBS; do
  pvesh set /cluster/backup/$job --storage SOURCE_STORAGE
done

# 3. Verify rollback
pvesh get /cluster/backup --output-format json | \
  jq '.[] | {id, storage}'
```

### Complete Rollback with Script

```bash
# Use migration script in reverse
./scripts/migrate_backup_storage.sh \
  --from TARGET_STORAGE \
  --to SOURCE_STORAGE \
  --all
```

## Troubleshooting

### Common Issues

#### 1. Target Storage Not Available

**Symptoms**: 
- Migration script reports storage not found
- `pvesm status` shows storage as inactive

**Solutions**:
```bash
# Check storage configuration
pvesh get /storage/TARGET_STORAGE

# Test storage connectivity
pvesm status TARGET_STORAGE

# Restart storage service if needed
systemctl restart pveproxy
```

#### 2. Insufficient Space on Target

**Symptoms**:
- Migration succeeds but backups fail
- PBS shows storage full errors

**Solutions**:
```bash
# Check available space
pvesm status | grep TARGET_STORAGE

# Clean old backups
proxmox-backup-client prune --repository TARGET_STORAGE

# Adjust retention policies
pvesh set /cluster/backup/JOB_ID --prune-backups 'keep-daily=2,keep-weekly=1'
```

#### 3. Permission Issues

**Symptoms**:
- API authentication failures
- Access denied errors

**Solutions**:
```bash
# Verify PBS user permissions
# In PBS web interface: Administration → Access Control

# Test PBS authentication
proxmox-backup-client list --repository root@pam@pbs-server:datastore
```

#### 4. Job Configuration Corruption

**Symptoms**:
- Jobs appear to migrate but don't run
- Invalid configuration errors

**Solutions**:
```bash
# Validate job configuration
pvesh get /cluster/backup/JOB_ID

# Recreate job from backup
# Use saved JSON configuration to manually recreate
```

## Post-Migration Tasks

### Cleanup

```bash
# Remove old backup data from source storage (if safe)
# ⚠️ CAUTION: Only after verifying new backups work

# Update documentation
# - Update infrastructure diagrams
# - Update monitoring alerts
# - Update disaster recovery procedures

# Update automation scripts
# - Backup monitoring scripts
# - Alerting configurations
# - Capacity planning tools
```

### Monitoring Setup

```bash
# Add monitoring for new storage
# Example: Add to monitoring stack

# Setup alerting for backup failures
# Example: Configure email notifications

# Schedule verification tests
# Add to cron for regular backup testing
```

## Maintenance Commands

### Regular Monitoring

```bash
# Daily storage check
pvesm status | grep backup

# Weekly backup verification
pvesh get /cluster/backup --output-format json | \
  jq '.[] | {id, storage, schedule, enabled}'

# Monthly capacity planning
df -h /path/to/backup/storage
```

### Emergency Procedures

```bash
# Emergency backup disable (all jobs)
for job in $(pvesh get /cluster/backup --output-format json | jq -r '.[].id'); do
  pvesh set /cluster/backup/$job --enabled 0
done

# Emergency backup enable (all jobs)  
for job in $(pvesh get /cluster/backup --output-format json | jq -r '.[].id'); do
  pvesh set /cluster/backup/$job --enabled 1
done
```

## Best Practices

### Planning
- Always test migration in non-production environment first
- Schedule migrations during maintenance windows
- Ensure adequate storage space (150% of current usage recommended)
- Document all custom configurations before migration

### Execution
- Use dry-run mode first to validate changes
- Monitor migration progress and storage usage
- Keep original configurations until migration is verified
- Test restore procedures after migration

### Security
- Use dedicated service accounts for PBS access
- Regularly rotate backup storage credentials
- Encrypt backup data in transit and at rest
- Audit backup access logs regularly

## Reference Information

### Related Documentation
- [Proxmox Infrastructure Guide](./proxmox-infrastructure-guide.md)
- [PBS Installation Guide](./pbs-installation-guide.md)
- [Backup Verification Procedures](./backup-verification-guide.md)

### Support Contacts
- Proxmox Documentation: https://pve.proxmox.com/wiki/Backup_and_Restore
- PBS Documentation: https://pbs.proxmox.com/docs/

### Script Locations
- Migration script: `/scripts/migrate_backup_storage.sh`
- Backup verification: `/scripts/verify_backups.sh`
- Storage monitoring: `/scripts/monitor_storage.sh`