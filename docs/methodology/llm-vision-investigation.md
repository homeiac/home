# LLM Vision Investigation Methodology

**Tool**: LLM Vision Home Assistant Integration
**Purpose**: Systematic investigation of LLM Vision timeline and functionality issues
**Based on**: Investigation discipline methodology + LLM Vision specific patterns

## LLM Vision Specific Investigation Sequence

### Phase 0: LLM Vision Documentation Review (MANDATORY)
1. **Read complete LLM Vision reference**: `docs/reference/llm-vision-complete-reference.md`
2. **Focus on timeline section**: Lines 164-216 (Timeline Card Configuration + Common Issues)
3. **Identify documented failure patterns**: Timeline shows "Off", entity issues, etc.
4. **Note diagnostic procedures**: Step-by-step troubleshooting from docs

### Phase 1: User Experience Classification
**Critical**: Understand exact user experience before technical investigation

#### Timeline Display Issues
- **"Off" display**: Timeline card shows "Off" instead of events
- **No events**: Timeline exists but shows no content
- **Wrong events**: Timeline shows events but content quality issues
- **Card missing**: Timeline card not visible in dashboard

#### Verification Questions
1. **What exactly do you see?** - Screenshot or exact description
2. **Timeline card installed?** - Via HACS frontend section
3. **Calendar entity exists?** - `calendar.llm_vision_timeline` in Developer Tools
4. **Events being created?** - Manual tests with `llmvision.remember` action

### Phase 2: Documented Diagnostic Sequence
**From docs/reference/llm-vision-complete-reference.md lines 212-216:**

#### Step 1: Calendar Entity Verification
```bash
# Check if calendar.llm_vision_timeline exists
curl -H "Authorization: Bearer $TOKEN" "$HA_URL/api/states/calendar.llm_vision_timeline"
```
**Success Criteria**: Entity exists and has attributes
**Failure Indicator**: 404 or entity not found

#### Step 2: Timeline Card Installation Check
- **Location**: HACS → Frontend → Search "LLM Vision Timeline Card"
- **Version**: Must match LLM Vision integration version
- **Card Configuration**: Verify entity: `calendar.llm_vision_timeline`

#### Step 3: Event Storage Test
```bash
# Manual event creation test
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Event", "summary": "Manual test event"}' \
  "$HA_URL/api/services/llmvision/remember"
```
**Success Criteria**: Event appears in calendar entity attributes
**Failure Indicator**: No event stored or API error

#### Step 4: Frontend Cache Verification
- **Clear browser cache** completely
- **Hard reload** (Ctrl+F5 or Cmd+Shift+R)
- **Restart Home Assistant** if cache issues persist

### Phase 3: MANDATORY Solution Verification (Home Assistant Specific)
**Before suggesting ANY LLM Vision solutions:**

#### Required System Access:
- **HA_TOKEN**: Available in `proxmox/homelab/.env` as `HOME_ASSISTANT_TOKEN`
- **HA_URL**: Available in `proxmox/homelab/.env` as `HOME_ASSISTANT_URL`

#### LLM Vision Specific Verification Commands (from RCA docs/troubleshooting/llm-vision-rca.md):
```bash
# Load environment variables
TOKEN=$(grep HOME_ASSISTANT_TOKEN proxmox/homelab/.env | cut -d'=' -f2)
URL=$(grep HOME_ASSISTANT_URL proxmox/homelab/.env | cut -d'=' -f2)

# Entity state verification (lines 110-111 from RCA)
curl -H "Authorization: Bearer $TOKEN" "$URL/api/states/calendar.llm_vision_timeline"

# Integration status check (lines 113-114 from RCA)
curl -H "Authorization: Bearer $TOKEN" "$URL/api/config/integrations" | jq '.[] | select(.domain == "llmvision")'

# Manual service testing (lines 122-125 from RCA)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"image_entity": "camera.test", "message": "test", "provider": "provider_id"}' \
  "$URL/api/services/llmvision/image_analyzer?return_response=true"

# Configuration investigation (lines 137-141 from RCA)
ssh -p 22222 root@homeassistant.maas "grep -A 15 'AI Event Summary' /mnt/data/supervisor/homeassistant/automations.yaml"

# Image verification (lines 161-162 from RCA) - CRITICAL for camera mapping
ssh -p 22222 root@homeassistant.maas "ls -lt /mnt/data/supervisor/homeassistant/www/llmvision/*.jpg | head -5"
scp -P 22222 root@homeassistant.maas:/mnt/data/supervisor/homeassistant/www/llmvision/RECENT_IMAGE.jpg /tmp/verify.jpg
```

#### Solution Verification Requirements:
- **Integration Existence**: Verify integration is properly configured and loaded
- **Entity State**: Confirm calendar entity exists and has events (not just "Off")
- **Service Testing**: Test actual API calls work with proposed parameters
- **Visual Verification**: Download and inspect actual captured images for camera mapping issues
- **Configuration Analysis**: Verify automation mapping arrays are aligned

#### If Verification Fails:
State: "Requires Home Assistant system access verification - check HOME_ASSISTANT_TOKEN and HOME_ASSISTANT_URL in proxmox/homelab/.env"

### Phase 4: Root Cause Classification

#### Timeline Card Installation Issues
**Symptoms**: Card shows error or "Off" display
**Root Cause**: Timeline card not installed via HACS Frontend
**Solution**: Install LLM Vision Timeline Card via HACS → Frontend

#### Calendar Entity Missing/Misconfigured  
**Symptoms**: Entity doesn't exist in Developer Tools → States
**Root Cause**: LLM Vision integration not properly configured
**Solution**: Reconfigure LLM Vision integration, check provider settings

#### Entity Configuration Mismatch
**Symptoms**: Timeline card configured but shows "Off"
**Root Cause**: Card pointing to wrong entity or entity misconfigured
**Solution**: Verify card configuration uses `calendar.llm_vision_timeline`

#### No Events Being Stored
**Symptoms**: Entity exists but no events in attributes
**Root Cause**: Actions not using `remember: true` or manual tests failing
**Solution**: Fix automation configuration or provider connectivity

## Investigation Command Limits

### Maximum Commands: 4
1. **Calendar entity check** - Verify `calendar.llm_vision_timeline` exists
2. **Manual event test** - Test `llmvision.remember` action  
3. **Entity attributes check** - Verify events stored in entity
4. **Timeline card config verify** - Check card entity configuration

### Documentation-First Approach
- **Use documented diagnostic steps** from reference guide
- **Follow troubleshooting sequence** from lines 205-216
- **Reference specific line numbers** when citing solutions
- **Complete local doc review** before any investigation commands

## Common Investigation Failures

### Assumption-Driven Diagnosis
❌ **Assuming camera mapping issues** without checking timeline card installation
❌ **Assuming content quality problems** when entity doesn't exist
❌ **Assuming complex technical issues** when simple configuration missing

### Documentation Shortcuts  
❌ **Keyword searching** instead of reading complete reference guide
❌ **Skipping diagnostic steps** in favor of random investigation
❌ **External web searches** before checking local documentation

### User Experience Misunderstanding
❌ **Technical investigation** without confirming what user actually sees
❌ **Complex solutions** for simple display/installation issues
❌ **Backend analysis** when frontend card is the actual problem

## Success Patterns

### Efficient Investigation
✅ **Read complete reference first** - understand all documented failure modes
✅ **Follow diagnostic sequence** - use documented steps in order
✅ **Verify user experience** - confirm exactly what they see
✅ **Simple solutions first** - check installation/configuration before complex debugging

### Documentation Usage
✅ **Reference specific lines** - cite docs/reference/llm-vision-complete-reference.md:205-216
✅ **Use documented commands** - follow exact diagnostic procedures from docs
✅ **Update methodology** - improve this guide based on investigation results

## Tool-Specific Knowledge Base

### LLM Vision Architecture
- **Integration**: Main LLM Vision custom component
- **Timeline Card**: Separate HACS frontend component  
- **Calendar Entity**: `calendar.llm_vision_timeline` stores events
- **Actions**: `llmvision.remember`, `llmvision.image_analyzer`, etc.

### Common Configuration Patterns
- **Timeline Card Entity**: Must point to `calendar.llm_vision_timeline`
- **Version Compatibility**: Integration and card versions must match
- **Event Storage**: Requires `remember: true` in action calls
- **Provider Setup**: AI provider must be configured for analysis actions

### Typical Failure Modes  
1. **Timeline card not installed** → Shows "Off" or error
2. **Entity configuration mismatch** → Card points to wrong entity
3. **Integration not configured** → Calendar entity doesn't exist
4. **No events stored** → Actions not using remember parameter
5. **Frontend cache issues** → Stale display after configuration changes

This methodology provides systematic LLM Vision investigation approach based on documented diagnostic procedures.