# PBS (Proxmox Backup Server) Storage Management

## Overview

Declarative, GitOps-style management for PBS storage entries in Proxmox VE. Inspired by Kubernetes/Crossplane patterns, this implementation allows you to manage PBS storage configuration as code.

## Features

✅ **Declarative Configuration**: Define PBS storage in YAML
✅ **DNS Validation**: Automatic DNS resolution and connectivity checks
✅ **PBS Health Checks**: Verifies port 8007 accessibility and SSL/TLS
✅ **Idempotent Reconciliation**: Safe to run multiple times
✅ **CLI Interface**: Rich terminal UI with tables and colors
✅ **Comprehensive Testing**: 25 unit tests, 74% coverage
✅ **Type-Safe**: Full type hints with mypy validation

## Quick Start

### 1. Configuration

Edit `config/pbs-storage.yaml`:

```yaml
pbs_storages:
  - name: homelab-backup
    enabled: true
    server: proxmox-backup-server.maas
    datastore: homelab-backup
    content:
      - backup
    username: root@pam
    fingerprint: "54:52:3A:D2:43:F0:80:66:E3:D0:BB:D6:0B:28:50:9F:C6:1C:73:BD:45:EA:D0:38:BC:25:54:EE:A4:D5:D1:54"
    prune_backups:
      keep_daily: 7
      keep_weekly: 4
      keep_monthly: 3
    description: "Primary PBS storage for homelab backups"
```

### 2. Validate Configuration

```bash
poetry run pbs validate --config config/pbs-storage.yaml --verbose
```

**Checks:**
- ✅ DNS resolution for PBS server hostname
- ✅ Port 8007 accessibility
- ✅ SSL/TLS handshake
- ✅ Fingerprint format validation
- ✅ Configuration syntax

**Example Output:**
```
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃ Storage          ┃ Status     ┃ DNS ┃ Port 8007 ┃ Issues ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│ homelab-backup   │ ✅ Valid   │ ✅  │ ✅        │ -      │
└──────────────────┴────────────┴─────┴───────────┴────────┘
```

### 3. View Current Status

```bash
poetry run pbs status
```

**Example Output:**
```
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Name                ┃ Server          ┃ Datastore      ┃ Status     ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ homelab-backup      │ pbs.maas        │ homelab-backup │ ✅ Enabled │
└─────────────────────┴─────────────────┴────────────────┴────────────┘
```

### 4. Apply Configuration

```bash
# Dry run (show what would change)
poetry run pbs apply --config config/pbs-storage.yaml --dry-run

# Actually apply changes
poetry run pbs apply --config config/pbs-storage.yaml
```

**Reconciliation Logic:**
- **Creates** missing storage entries
- **Updates** existing entries to match config
- **Enables** storage marked as `enabled: true`
- **Disables** storage marked as `enabled: false`

## Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│  config/pbs-storage.yaml                            │
│  (Declarative configuration)                        │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  PBSStorageManager                                  │
│  - load_config()                                    │
│  - validate_storage_config()                        │
│  - reconcile_storage()                              │
│  - check_pbs_connectivity()                         │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  Proxmox API                                        │
│  - storage.create()                                 │
│  - storage().put()                                  │
│  - storage().get()                                  │
└─────────────────────────────────────────────────────┘
```

### Files

| File | Purpose |
|------|---------|
| `config/pbs-storage.yaml` | Declarative configuration (single source of truth) |
| `src/homelab/pbs_storage_manager.py` | Core reconciliation logic |
| `src/homelab/pbs_cli.py` | CLI interface (validate, apply, status) |
| `tests/test_pbs_storage_manager.py` | Unit tests (25 tests, 74% coverage) |
| `pyproject.toml` | Package config, scripts: `pbs = "homelab.pbs_cli:app"` |

## Configuration Reference

### Storage Entry Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | ✅ | string | Storage identifier (unique) |
| `enabled` | ❌ | boolean | Enable/disable storage (default: `true`) |
| `server` | ✅ | string | PBS server hostname/IP |
| `datastore` | ✅ | string | PBS datastore name |
| `content` | ❌ | list | Content types (default: `["backup"]`) |
| `username` | ❌ | string | PBS username (default: `"root@pam"`) |
| `fingerprint` | ✅ | string | PBS SSL fingerprint (SHA-256) |
| `prune_backups` | ❌ | object | Backup retention policy |
| `description` | ❌ | string | Human-readable description |

### Prune Backups Options

```yaml
prune_backups:
  keep_daily: 7      # Keep 7 daily backups
  keep_weekly: 4     # Keep 4 weekly backups
  keep_monthly: 3    # Keep 3 monthly backups
  keep_yearly: 1     # Keep 1 yearly backup
  keep_all: 1        # Keep all backups (not recommended)
```

**Note**: Snake_case in YAML converts to kebab-case for Proxmox API (`keep_daily` → `keep-daily`)

## DNS Resolution Requirements

### Why DNS Matters

PBS storage configuration uses **hostnames** (`proxmox-backup-server.maas`), not IP addresses. This requires proper DNS setup:

1. **MAAS DNS**: Manages `.maas` domain entries (192.168.4.53)
2. **OPNsense DNS**: Manages `.homelab` domain entries (192.168.4.1)

### DNS Validation Flow

```
PBSStorageManager.validate_storage_config()
  │
  ├─> resolve_hostname(server)
  │   └─> socket.gethostbyname() → IP address
  │
  ├─> check_pbs_connectivity(server, port=8007)
  │   ├─> DNS resolution check
  │   ├─> TCP connectivity check (port 8007)
  │   └─> SSL/TLS handshake check
  │
  └─> Return validation results (errors/warnings)
```

### Common DNS Issues

#### Issue: DNS resolution failed for proxmox-backup-server.maas

**Symptoms:**
```
❌ DNS resolution failed for proxmox-backup-server.maas.
   Add DNS entry in MAAS: proxmox-backup-server.maas -> <PBS_IP>
```

**Solution**: Add DNS entry in MAAS web GUI:
1. Go to http://192.168.4.53:5240/MAAS/
2. DNS → maas domain → "Add DNS resource"
3. Name: `proxmox-backup-server`, IP: `<PBS_IP>`

**Why CLI created entries disappear**: MAAS garbage-collects DNS resources for non-managed IPs. Use web GUI for permanent entries.

## Usage Examples

### Example 1: Enable Disabled Storage

**config/pbs-storage.yaml:**
```yaml
pbs_storages:
  - name: old-pbs-storage
    enabled: true  # Change from false to true
    server: pbs.maas
    datastore: old-backups
    fingerprint: "AA:BB:CC:..."
```

**Apply:**
```bash
poetry run pbs apply --config config/pbs-storage.yaml
```

**Output:**
```
🔓 Enabled storage old-pbs-storage
📝 Updated storage old-pbs-storage
```

### Example 2: Disable Misconfigured Storage

**config/pbs-storage.yaml:**
```yaml
pbs_storages:
  - name: broken-storage
    enabled: false  # Disable instead of delete
    server: pbs.maas
    datastore: nonexistent
    fingerprint: "AA:BB:CC:..."
```

**Apply:**
```bash
poetry run pbs apply --config config/pbs-storage.yaml
```

**Output:**
```
🔒 Disabled storage broken-storage
```

### Example 3: Skip Validation (Advanced)

**Use case**: DNS not available from management host, but works from Proxmox nodes.

```bash
poetry run pbs apply --config config/pbs-storage.yaml --skip-validation
```

**Warning**: Only use when DNS/connectivity issues are expected from the management host but known to work from Proxmox nodes.

## Development

### Running Tests

```bash
# Run all PBS tests
poetry run pytest tests/test_pbs_storage_manager.py -v

# Run with coverage report
poetry run pytest tests/test_pbs_storage_manager.py --cov=src/homelab/pbs_storage_manager --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Test Coverage

- **25 tests** covering all major functionality
- **74% coverage** of pbs_storage_manager.py
- Comprehensive mocking of Proxmox API, DNS, network calls

### Code Quality

```bash
# Type checking
poetry run mypy src/homelab/pbs_storage_manager.py

# Code formatting
poetry run black src/homelab/pbs_storage_manager.py

# Import sorting
poetry run isort src/homelab/pbs_storage_manager.py

# Linting
poetry run flake8 src/homelab/pbs_storage_manager.py
```

## Troubleshooting

### Validation Fails: DNS Resolution

**Problem**: `❌ DNS resolution failed`

**Debug**:
```bash
# Test DNS from management host
nslookup proxmox-backup-server.maas 192.168.4.53

# Test DNS from Proxmox host
ssh root@pve.maas "nslookup proxmox-backup-server.maas"
```

**Solutions**:
1. Add DNS entry in MAAS web GUI (permanent)
2. Use `--skip-validation` flag (temporary workaround)
3. Add entry to `/etc/hosts` on Proxmox hosts (not recommended)

### Validation Fails: Port 8007 Not Reachable

**Problem**: `❌ PBS port 8007 not reachable`

**Debug**:
```bash
# Check if PBS is running
ssh root@pbs-host "systemctl status proxmox-backup"

# Test port accessibility
ssh root@pve.maas "nc -zv proxmox-backup-server.maas 8007"
```

**Solutions**:
1. Start PBS service: `systemctl start proxmox-backup`
2. Check firewall rules on PBS host
3. Verify PBS is listening on 8007: `ss -tunlp | grep 8007`

### Apply Fails: Fingerprint Mismatch

**Problem**: `❌ Fingerprint appears invalid`

**Debug**:
```bash
# Get current fingerprint from PBS
ssh root@pve.maas "pvesm set homelab-backup --fingerprint \$(openssl s_client -connect proxmox-backup-server.maas:8007 2>/dev/null | openssl x509 -fingerprint -sha256 -noout | cut -d'=' -f2)"
```

**Solution**: Update fingerprint in config file to match actual PBS certificate.

## Best Practices

1. **Always validate before applying**:
   ```bash
   poetry run pbs validate && poetry run pbs apply
   ```

2. **Use dry-run for safety**:
   ```bash
   poetry run pbs apply --dry-run
   ```

3. **Keep config in version control**:
   ```bash
   git add config/pbs-storage.yaml
   git commit -m "feat: update PBS backup retention policy"
   ```

4. **Document changes in config file**:
   ```yaml
   # 2025-11-12: Increased retention for compliance requirements
   prune_backups:
     keep_daily: 30  # Was: 7
   ```

5. **Test DNS from Proxmox hosts** (not just management host)

## Future Enhancements

- [ ] Support for multiple PBS servers
- [ ] Automatic fingerprint retrieval and validation
- [ ] Backup verification and restore testing
- [ ] Integration with monitoring (Uptime Kuma/Prometheus)
- [ ] Automatic datastore creation on PBS
- [ ] Support for PBS namespaces
- [ ] GitOps automation (auto-apply on config changes)

## Related Documentation

- [Proxmox Backup Server Storage Connectivity Runbook](../docs/runbooks/proxmox-backup-server-storage-connectivity.md)
- [DNS Configuration Guide](../docs/source/md/dns-configuration-guide.md)
- [MAAS DNS Forwarding Investigation](../docs/source/md/maas-dns-forwarding-investigation.md)

## Tags

`pbs`, `proxmox-backup-server`, `storage`, `declarative`, `gitops`, `dns`, `validation`, `homelab`, `infrastructure-as-code`
