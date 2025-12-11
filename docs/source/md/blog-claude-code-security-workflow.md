# Using Claude Code to Keep My Repository Secure

*How AI-assisted dependency management turns Dependabot alerts into quick fixes*

---

```
    +-------------------+     Push      +-------------------+
    |   Local Repo      |-------------->|     GitHub        |
    |                   |               |                   |
    +-------------------+               +-------------------+
            ^                                   |
            |                                   v
    +-------------------+               +-------------------+
    |   Claude Code     |<--------------|   Dependabot      |
    |   "fix security"  |   7 alerts    |   Security Scan   |
    +-------------------+               +-------------------+
            |
            v
    +-------------------+
    |   Updated Deps    |
    |   urllib3 2.6.2   |
    +-------------------+
```

## The Problem

Every time I push to my homelab repository, I see the dreaded message:

```
remote: GitHub found 7 vulnerabilities on homeiac/home's default branch
remote: (6 high, 1 moderate).
```

Manually tracking down which packages need updates across multiple `poetry.lock` files, understanding which vulnerabilities are fixable versus blocked by upstream constraints, and crafting appropriate commit messages is tedious. This is exactly the kind of work that AI assistants excel at.

## The Workflow

### Step 1: Trigger the Fix

I simply tell Claude Code:

```
fix the security issues
```

That's it. No need to specify which vulnerabilities, which files, or which versions.

### Step 2: Claude Investigates

Claude immediately:

1. **Queries the GitHub API** to get the actual Dependabot alerts:
   ```bash
   gh api repos/homeiac/home/dependabot/alerts
   ```

2. **Identifies affected files** by searching for dependency manifests:
   - `**/poetry.lock`
   - `**/pyproject.toml`
   - `**/package.json`
   - `**/requirements.txt`

3. **Analyzes each vulnerability** by searching for CVE details and fix versions

### Step 3: Claude Fixes What Can Be Fixed

In my case, Claude found 7 open vulnerabilities:

| Package | CVE | Severity | Location | Status |
|---------|-----|----------|----------|--------|
| urllib3 | CVE-2025-66471 | High | proxmox/homelab | **Fixed** |
| urllib3 | CVE-2025-66418 | High | proxmox/homelab | **Fixed** |
| urllib3 | CVE-2025-66471 | High | esp32-status-puck | **Fixed** |
| urllib3 | CVE-2025-66418 | High | esp32-status-puck | **Fixed** |
| starlette | CVE-2025-62727 | High | esp32-status-puck | Blocked |
| starlette | CVE-2024-47874 | Medium | esp32-status-puck | Blocked |
| ecdsa | CVE-2024-23342 | High | esp32-status-puck | No fix |

Claude ran:
```bash
cd proxmox/homelab && poetry update urllib3
cd esp32-status-puck/firmware && poetry update urllib3
```

### Step 4: Claude Explains What Can't Be Fixed

This is where Claude really shines. Instead of just failing silently or leaving me confused, Claude explained:

**starlette (CVE-2025-62727, CVE-2024-47874):**
> "platformio 6.1.18 requires `starlette <0.47`, but the fix requires `>=0.49.1`. The constraint comes from an upstream dependency that hasn't released a compatible version yet."

**ecdsa (CVE-2024-23342):**
> "The maintainers have stated they will not fix this vulnerability. From the security advisory: 'side-channel vulnerabilities are outside the scope of the project... implementing side-channel free code in pure python is impossible.'"

This context is invaluable. I now know:
- Which vulnerabilities will resolve themselves when upstream releases updates
- Which vulnerabilities are architectural and require replacing the library entirely

### Step 5: Claude Commits with Context

The commit message Claude generated:

```
fix(security): update urllib3 to 2.6.2 to fix CVE-2025-66471 and CVE-2025-66418

Updates urllib3 from 2.5.0 to 2.6.2 in both proxmox/homelab and
esp32-status-puck/firmware to address:
- CVE-2025-66471: Streaming API improperly handles highly compressed data
- CVE-2025-66418: Unbounded number of links in decompression chain

Note: 3 vulnerabilities remain unfixable in esp32-status-puck:
- starlette CVE-2025-62727: Blocked by platformio requiring <0.47
- starlette CVE-2024-47874: Same constraint issue
- ecdsa CVE-2024-23342: Upstream won't fix (side-channel out of scope)
```

This commit message is:
- **Scannable**: Clear title with CVE numbers
- **Complete**: Lists what was fixed and what wasn't
- **Actionable**: Future me knows exactly what to monitor

## Why This Works Better Than Manual Updates

### 1. Cross-Ecosystem Understanding

My repo has Python (Poetry), JavaScript (npm), and documentation dependencies. Claude handles all of them in one pass, understanding the different tooling for each:

- `poetry update` for Python
- `npm update` for JavaScript
- Knows to check both direct and transitive dependencies

### 2. Constraint Analysis

When Claude encounters a blocked upgrade, it doesn't just say "can't update." It:
- Identifies which package is blocking
- Explains the version constraint
- Checks if newer versions of the blocker exist
- Reports whether this is a temporary or permanent limitation

### 3. Research Integration

Claude searched the web to find:
- The exact fix version for each CVE
- Whether maintainers plan to address the issue
- Alternative libraries if the original won't be fixed

### 4. Audit Trail

Every security fix includes:
- CVE numbers for tracking
- Before/after versions
- Explanation of unfixable issues
- Links to security advisories

## The Commands I Actually Use

```bash
# Full security audit and fix
claude "fix the security issues"

# Check specific ecosystem
claude "update all Python dependencies with security vulnerabilities"

# Audit without fixing
claude "what security vulnerabilities exist in this repo?"
```

## Integrating with CI/CD

I could automate this further with a GitHub Action that:
1. Runs on Dependabot alert creation
2. Invokes Claude Code to attempt fixes
3. Creates a PR with the fixes and explanations
4. Tags unfixable issues for manual review

But honestly, the manual "fix the security issues" command takes about 30 seconds and gives me visibility into what's changing. For a homelab, that's the right balance.

## Lessons Learned

### What Claude Does Well
- **Comprehensive investigation**: Checks all dependency files, not just the obvious ones
- **Constraint resolution**: Understands why some updates are blocked
- **Documentation**: Commit messages that future-me will appreciate
- **Web research**: Finds CVE details and fix versions automatically

### What Still Needs Human Judgment
- **Risk assessment**: Is a "won't fix" vulnerability actually a risk in my use case?
- **Alternative selection**: If a library won't be fixed, what should replace it?
- **Breaking changes**: Major version updates might need manual testing

## The Bottom Line

Security maintenance used to be a chore I'd put off until the Dependabot warnings became embarrassing. Now it's a 30-second interaction:

```
> fix the security issues

Fixed 4/7 vulnerabilities. 3 remain unfixable:
- starlette: blocked by platformio constraint
- ecdsa: upstream won't fix

Committed and pushed.
```

The AI handles the tedious parts (finding versions, updating lock files, writing commit messages) while surfacing the decisions that actually need human input (should I replace ecdsa with a different library?).

That's the sweet spot for AI-assisted development: not replacing judgment, but eliminating busywork so I can focus on the decisions that matter.

## The Result

Before:
```
remote: GitHub found 7 vulnerabilities on homeiac/home's default branch (6 high, 1 moderate).
```

After:
```
remote: GitHub found 3 vulnerabilities on homeiac/home's default branch (2 high, 1 moderate).
```

**4 high-severity vulnerabilities resolved in under a minute.** The remaining 3 are documented, explained, and tracked - waiting for upstream fixes that are out of my control.

---

*Written after Claude Code fixed my urllib3 vulnerabilities in December 2025*
