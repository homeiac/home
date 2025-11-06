# GitHub Issues for Proxmox Terraform Code Review

Created: 2025-11-06
Branch: `claude/review-proxmox-terraform-code-011CUqhjRtB4UEcWUPvSYSUe`

---

## Issue 1: [CRITICAL] Fix config.py import-time side effects breaking tests

**Priority**: CRITICAL
**Labels**: bug, critical, testing, technical-debt

### Problem

**Location**: `src/homelab/config.py:27`

The Config class attempts to read SSH public key at module import time, causing all tests to fail if the file doesn't exist:

```python
# Lines 26-28 - BREAKS ALL TESTS
_SSH_PATH = os.path.expanduser(os.getenv("SSH_PUBKEY_PATH", "~/.ssh/id_rsa.pub"))
with open(_SSH_PATH) as _f:  # ❌ FAILS AT IMPORT TIME
    raw_ssh = _f.read().strip()
```

### Impact

- **All 307 tests fail during collection** without creating dummy SSH keys
- Violates lazy initialization principle
- Makes mocking impossible
- Prevents CI/CD pipeline execution

### Proposed Solution

Replace module-level file I/O with lazy-loaded property:

```python
@property
def SSH_PUBKEY(self) -> str:
    """Load SSH public key on demand."""
    if not hasattr(self, '_ssh_pubkey'):
        ssh_path = os.path.expanduser(os.getenv("SSH_PUBKEY_PATH", "~/.ssh/id_rsa.pub"))
        try:
            with open(ssh_path) as f:
                raw_ssh = f.read().strip()
            self._ssh_pubkey = quote(raw_ssh, safe="")
        except FileNotFoundError:
            raise ValueError(f"SSH public key not found at {ssh_path}")
    return self._ssh_pubkey
```

### Acceptance Criteria

- [ ] SSH key loaded lazily (not at import time)
- [ ] Tests can run without creating dummy SSH keys
- [ ] Proper error handling with informative messages
- [ ] All tests pass collection phase
- [ ] Update all references to `Config.SSH_PUBKEY` (should be property access)

### Related Files

- `src/homelab/config.py`
- `tests/conftest.py`
- All test files that import from homelab modules

---

## Issue 2: [HIGH] Fix 93 failing tests (30% failure rate)

**Priority**: HIGH
**Labels**: testing, bug, quality

### Problem

Current test status: **214 passing, 93 failing (70% pass rate)**

Tests fail in three main categories:

1. **Environment Issues** (23 failures):
   - Missing `API_TOKEN` environment variable
   - Tests expecting `.env` configuration

2. **Network Isolation Failures** (45 failures):
   - Tests making real DNS lookups (`socket.gaierror`)
   - Tests attempting real SSH connections
   - Tests not properly mocked

3. **Assertion Errors** (25 failures):
   - Mock expectations not matching actual calls
   - Test data inconsistencies

### Example Failures

```python
# test_proxmox_api.py:test_proxmox_client_init
# Test expects host without suffix, code appends ".maas"
mock_proxmox.assert_called_once_with(host="test-node.maas")  # ❌ Fails

# test_monitoring_manager.py::test_container_exists_true
# socket.gaierror - test trying real DNS lookup
```

### Proposed Solution

1. **Fix environment mocking** in `tests/conftest.py`:
   ```python
   @pytest.fixture
   def complete_env(monkeypatch):
       """Complete environment setup for all tests."""
       monkeypatch.setenv("API_TOKEN", "test!token=secret")
       monkeypatch.setenv("SSH_PUBKEY_PATH", "/tmp/test_key.pub")
       # ... all required env vars
   ```

2. **Fix network isolation**:
   - Mock all SSH connections
   - Mock all DNS lookups
   - Mock all HTTP requests

3. **Update assertions** to match actual code behavior

### Acceptance Criteria

- [ ] All 307 tests pass
- [ ] No tests make real network calls
- [ ] Tests run without .env file
- [ ] Tests run in isolated environment
- [ ] Coverage report generation succeeds

### Related Files

- `tests/conftest.py`
- `tests/test_proxmox_api.py`
- `tests/test_monitoring_manager.py`
- `tests/test_vm_manager.py`
- All test files with network operations

---

## Issue 3: [HIGH] Fix 43 mypy type safety errors

**Priority**: HIGH
**Labels**: type-safety, quality, technical-debt

### Problem

Mypy reports 43 type errors across 10 files preventing strict type checking.

### Major Error Categories

1. **Missing type hints** (10 errors):
   ```python
   # src/homelab/pumped_piglet_migration.py:176
   def _parse_node_status(output):  # ❌ No type annotations
   ```

2. **Incorrect return types** (8 errors):
   ```python
   # src/homelab/uptime_kuma_client.py:107
   def get_monitors(self) -> dict[str, Any]:
       return self.api.get_monitors()  # ❌ Returns Any
   ```

3. **Invalid type usage** (6 errors):
   ```python
   # src/homelab/coral_initialization.py:210
   def run_initialization_script(...) -> Optional[any]:  # ❌ Should be typing.Any
   ```

4. **Untyped decorators** (12 errors):
   ```python
   # All CLI commands in cli.py
   @app.command()  # ❌ Untyped decorator makes function untyped
   def init_config(...):
   ```

5. **Missing library stubs** (7 errors):
   - requests (need `types-requests`)
   - typer, rich (need stubs or ignore)

### Files Affected

- `src/homelab/crucible_config.py` (2 errors)
- `src/homelab/iso_manager.py` (3 errors)
- `src/homelab/uptime_kuma_client.py` (3 errors)
- `src/homelab/monitoring_manager.py` (9 errors)
- `src/homelab/coral_config.py` (3 errors)
- `src/homelab/pumped_piglet_migration.py` (5 errors)
- `src/homelab/coral_initialization.py` (1 error)
- `src/homelab/coral_automation.py` (1 error)
- `src/homelab/oxide_storage_api.py` (1 error)
- `src/homelab/cli.py` (15 errors)

### Acceptance Criteria

- [ ] `poetry run mypy src/homelab/` reports 0 errors
- [ ] All functions have proper type hints
- [ ] No `Any` return types without justification
- [ ] Proper Optional/Union usage
- [ ] Type stubs installed for external libraries

### Testing Command

```bash
cd proxmox/homelab
poetry run mypy src/homelab/ --show-error-codes
```

---

## Issue 4: [MEDIUM] Code style compliance - format with black, flake8, isort

**Priority**: MEDIUM
**Labels**: code-style, quality

### Problem

Code style violations prevent pre-commit checks from passing:

1. **Black formatting**: 16/25 files need reformatting
2. **Flake8 violations**: 50+ style errors
3. **Isort**: 3 files with incorrect import order

### Specific Violations

#### Black (16 files)
- cli.py, coral_automation.py, coral_config.py
- coral_detection.py, coral_initialization.py, coral_models.py
- crucible_config.py, crucible_mock.py, development_manager.py
- enhanced_vm_manager.py, k3s_migration_manager.py
- oxide_storage_api.py, pumped_piglet_migration.py
- storage_manager.py, uptime_kuma_client.py, vm_manager.py

#### Flake8 (50+ violations)
- **W293**: Blank lines with whitespace (45 in cli.py)
- **F401**: Unused imports (`typing.List`, `SnapshotCreate`)
- **F841**: Unused variables (`config_dict`)
- **F541**: f-strings without placeholders

#### Isort (3 files)
- enhanced_vm_manager.py
- coral_config.py
- coral_automation.py

### Acceptance Criteria

- [ ] `poetry run black src/homelab/` - all files formatted
- [ ] `poetry run flake8 src/homelab/` - 0 violations
- [ ] `poetry run isort src/homelab/` - all imports sorted
- [ ] Pre-commit checks pass

### Commands to Fix

```bash
cd proxmox/homelab

# Auto-fix formatting
poetry run black src/homelab/
poetry run isort src/homelab/

# Verify
poetry run black --check src/homelab/
poetry run flake8 src/homelab/ --max-line-length=120 --extend-ignore=E203,W503
poetry run isort --check-only src/homelab/
```

---

## Issue 5: [MEDIUM] Replace 113 print() statements with proper logging

**Priority**: MEDIUM
**Labels**: quality, logging, technical-debt

### Problem

113 `print()` statements across 8 files violate logging best practices:

- Cannot control log levels
- No structured logging
- Difficult to filter/analyze
- No timestamps or context

### Files Affected

```
cli.py:                 22 print() calls
enhanced_vm_manager.py:  6 print() calls
proxmox_api.py:          3 print() calls
iso_manager.py:          5 print() calls
vm_manager.py:          15 print() calls
config.py:               1 print() call
uptime_kuma_client.py:  24 print() calls
monitoring_manager.py:  37 print() calls
```

### Examples

```python
# Bad (vm_manager.py:70)
print(f"💾 Importing {os.path.basename(img_path)} → {storage} on {host}")

# Good
logger.info(f"Importing {os.path.basename(img_path)} to {storage} on {host}")

# Bad (proxmox_api.py:34)
print(f"host: {self.host}")

# Good
logger.debug(f"ProxmoxClient connected to host: {self.host}")
```

### Acceptance Criteria

- [ ] All `print()` replaced with appropriate logger calls
- [ ] Use appropriate log levels (debug, info, warning, error)
- [ ] Remove emoji (not suitable for logs) or make configurable
- [ ] Consistent logging format across all modules
- [ ] No print() statements in src/homelab/ (except CLI output)

### Log Level Guidelines

- `logger.debug()` - Detailed diagnostic information
- `logger.info()` - General informational messages
- `logger.warning()` - Warning messages
- `logger.error()` - Error messages
- CLI output can use `print()` for user-facing output only

---

## Issue 6: [LOW] Refactor large classes and functions

**Priority**: LOW
**Labels**: refactoring, technical-debt, maintainability

### Problem

Several files have grown too large and violate single responsibility principle:

1. **pumped_piglet_migration.py** - 778 lines
2. **monitoring_manager.py** - 687 lines
3. **oxide_storage_api.py** - 659 lines
4. **enhanced_vm_manager.py** - 573 lines

Large functions:
- `create_or_update_vm()` - 102 lines (vm_manager.py:113-216)

### Proposed Refactoring

#### MonitoringManager (687 lines)

**Current**: God object handling SSH, Docker, LXC, Proxmox

**Proposed Split**:
```
monitoring_manager.py (orchestrator - 150 lines)
  ├── ssh_client.py (SSH operations - 100 lines)
  ├── docker_manager.py (Docker operations - 150 lines)
  ├── lxc_manager.py (LXC operations - 150 lines)
  └── uptime_kuma_deployer.py (Uptime Kuma - 150 lines)
```

#### VMManager.create_or_update_vm() (102 lines)

**Proposed Split**:
```python
def create_or_update_vm(self) -> None:
    """Main orchestrator - delegates to smaller methods."""
    for node in self._get_nodes_to_process():
        if self._should_skip_node(node):
            continue

        vm_config = self._prepare_vm_config(node)
        self._create_vm_shell(node, vm_config)
        self._setup_vm_storage(node, vm_config)
        self._configure_cloud_init(node, vm_config)
        self._start_and_wait_for_vm(node, vm_config)
```

### Acceptance Criteria

- [ ] No file exceeds 500 lines
- [ ] No function exceeds 50 lines
- [ ] Single responsibility per class
- [ ] Better testability (smaller units)
- [ ] All tests still pass after refactoring

### Files to Refactor

- `src/homelab/pumped_piglet_migration.py`
- `src/homelab/monitoring_manager.py`
- `src/homelab/oxide_storage_api.py`
- `src/homelab/enhanced_vm_manager.py`
- `src/homelab/vm_manager.py` (create_or_update_vm function)

---

## Issue 7: [MEDIUM] Fix static method overuse and implement dependency injection

**Priority**: MEDIUM
**Labels**: architecture, technical-debt

### Problem

Heavy use of `@staticmethod` makes testing difficult and prevents proper dependency injection:

```python
class VMManager:
    @staticmethod  # ❌ Makes testing harder, no shared state
    def vm_exists(proxmox: Any, node_name: str) -> Optional[int]:
        ...

    @staticmethod
    def get_next_available_vmid(proxmox: Any) -> int:
        ...
```

**Issues**:
1. Hard to mock Proxmox client
2. No shared configuration state
3. Forces `proxmox: Any` type (loses type safety)
4. Each method receives same dependencies repeatedly

### Proposed Solution

Convert to instance methods with dependency injection:

```python
class VMManager:
    """Manages VM lifecycle on Proxmox cluster."""

    def __init__(self, proxmox: ProxmoxAPI, config: Config):
        """Initialize VM manager with dependencies.

        Args:
            proxmox: Proxmox API client
            config: Configuration object
        """
        self.proxmox = proxmox
        self.config = config

    def vm_exists(self, node_name: str) -> Optional[int]:
        """Check if VM exists on node.

        Args:
            node_name: Name of Proxmox node

        Returns:
            VM ID if exists, None otherwise
        """
        expected = self.config.VM_NAME_TEMPLATE.format(node=node_name.replace("_", "-"))
        for vm in self.proxmox.nodes(node_name).qemu.get():
            if vm.get("name") == expected:
                return int(vm["vmid"])
        return None
```

### Benefits

1. **Easier testing**: Mock dependencies at construction
2. **Type safety**: Proper `ProxmoxAPI` type instead of `Any`
3. **Shared state**: Configuration loaded once
4. **Cleaner API**: Methods don't repeat parameters

### Acceptance Criteria

- [ ] VMManager uses instance methods
- [ ] ProxmoxClient injected at construction
- [ ] Config injected at construction
- [ ] All tests updated to use new pattern
- [ ] Type hints use `ProxmoxAPI` not `Any`
- [ ] Tests still pass (mocking at __init__)

### Files to Update

- `src/homelab/vm_manager.py`
- `src/homelab/resource_manager.py`
- `tests/test_vm_manager.py`

---

## Issue 8: [LOW] Add missing docstrings and improve documentation

**Priority**: LOW
**Labels**: documentation, quality

### Problem

Many functions lack proper documentation:

1. **Private methods** missing docstrings:
   - `_import_disk_via_cli()`
   - `_resize_disk_via_cli()`
   - `_get_vm_mac_address()`

2. **Missing Args/Returns sections** in existing docstrings

3. **No examples** in complex functions

### Acceptance Criteria

- [ ] All public methods have Google-style docstrings
- [ ] All docstrings include Args, Returns, Raises sections
- [ ] Complex functions have usage examples
- [ ] Private methods have brief docstrings
- [ ] Module docstrings explain purpose and usage

### Example Template

```python
def deploy_uptime_kuma(self, node: str, lxc_id: Optional[int] = None) -> Dict[str, Any]:
    """Deploy Uptime Kuma monitoring container on Proxmox node.

    This method deploys Uptime Kuma either in a Docker container (if Docker is available)
    or in a new LXC container. The deployment is idempotent - running multiple times
    won't create duplicate instances.

    Args:
        node: Proxmox node name (e.g., 'pve', 'fun-bedbug')
        lxc_id: Optional LXC container ID. If provided, deploys in existing LXC.
                If None, will find Docker-enabled LXC or create new one.

    Returns:
        Dictionary containing deployment status:
        {
            'status': 'created' | 'existing' | 'error',
            'container_id': str,
            'ip_address': str,
            'url': str
        }

    Raises:
        ProxmoxAPIError: If Proxmox API call fails
        SSHConnectionError: If SSH connection to node fails
        TimeoutError: If deployment takes longer than 5 minutes

    Example:
        >>> manager = MonitoringManager()
        >>> result = manager.deploy_uptime_kuma('pve')
        >>> print(result['url'])
        http://192.168.4.194:3001
    """
```

---

## Summary of Issues

| # | Title | Priority | Category | Est. Effort |
|---|-------|----------|----------|-------------|
| 1 | Fix config.py import-time side effects | CRITICAL | Bug | 2 hours |
| 2 | Fix 93 failing tests | HIGH | Testing | 2 days |
| 3 | Fix 43 mypy type errors | HIGH | Type Safety | 1 day |
| 4 | Code style compliance | MEDIUM | Quality | 2 hours |
| 5 | Replace print() with logging | MEDIUM | Quality | 4 hours |
| 6 | Refactor large classes | LOW | Refactoring | 3 days |
| 7 | Fix static method overuse | MEDIUM | Architecture | 1 day |
| 8 | Add missing docstrings | LOW | Documentation | 1 day |

**Total Estimated Effort**: ~9 days

## Recommended Order

1. **Issue #1** (CRITICAL) - Unblocks all testing
2. **Issue #4** (MEDIUM) - Quick wins, auto-fixable
3. **Issue #5** (MEDIUM) - Improves debugging
4. **Issue #2** (HIGH) - Get tests passing
5. **Issue #3** (HIGH) - Type safety
6. **Issue #7** (MEDIUM) - Architecture improvements
7. **Issue #8** (LOW) - Documentation
8. **Issue #6** (LOW) - Large refactoring

---

## Branch Information

**Branch**: `claude/review-proxmox-terraform-code-011CUqhjRtB4UEcWUPvSYSUe`

All fixes should be committed to this branch with references to these issues:

```bash
git add <files>
git commit -m "fix: <description> (fixes #<issue-number>)"
git push -u origin claude/review-proxmox-terraform-code-011CUqhjRtB4UEcWUPvSYSUe
```
