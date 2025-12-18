# Voice PE Approval - Implementation Plan

## Day 0: MVP Shipped ✅

Ship it, quirks and all. Find market fit.

**What works**:
- Voice command → Claude → response
- Approval request → LED → dial/button → response
- RequestId correlation
- Server-side timeout

**Known quirks** (acceptable for Day 0):
- Voice yes/no NOT tested
- Edge cases in dial/button handling
- No HA-side timeout feedback

**Status**: Deployed. Usable.

---

## Day 1: It Takes Off

Real usage. Fix bugs. Make it reliable.

| Issue | Impact | Fix |
|-------|--------|-----|
| **Voice yes/no** | Can't approve hands-free | Add intent + guard |
| **Spurious dial events** | Accidental approve/reject | Tighten guard logic |
| **Timeout feedback** | LED stuck orange | Clear on server timeout |
| **Error silence** | User doesn't know it failed | TTS error messages |

**Day 1 Definition of Done**:
- [ ] Voice yes/no works
- [ ] No spurious approvals from idle state
- [ ] Clean state reset after any outcome
- [ ] Errors are spoken, not silent

---

## Day 2: Carrying Water

The boring but critical stuff.

| Area | Work |
|------|------|
| **Testing** | Organize 65 scripts → test suite with runner |
| **CI/CD** | GitOps for HA automation deployment |
| **Observability** | Structured logs, requestId tracing |
| **Docs** | Runbook for common issues |

**Day 2 Definition of Done**:
- [ ] `./run-tests.sh` passes
- [ ] Deploy via git push
- [ ] Can trace request end-to-end
- [ ] Runbook exists

---

## MVP++ (Full Scenarios)

After Day 1/2 foundations:

| Scenario | When |
|----------|------|
| 1. Simple question | ✅ Day 0 |
| 2. Binary approval | Day 1 |
| 3. Multiple approvals | MVP++ |
| 4. Follow-up/context | MVP++ |
| 5. Error handling | Day 1/2 |
| 6. Multiple choice | MVP++ |

---

## V2

| Feature | Notes |
|---------|-------|
| Resume conversation | Beyond timeout |
| Cancel execution | SIGINT |
| Two-step preview | Accidental approval prevention |

---

## Principal Criteria

| -ility | Bar |
|--------|-----|
| **Testability** | Automated test per scenario |
| **Maintainability** | Single automation, DRY |
| **Observability** | RequestId tracing |
| **Reliability** | Graceful timeout/error handling |
| **Usability** | Clear feedback every state |
