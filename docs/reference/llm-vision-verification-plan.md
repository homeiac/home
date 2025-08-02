# LLM Vision Complete Verification Plan

## Phase 1: Integration Installation Verification

### Step 1: HACS Installation Check
- [ ] **Verify HACS Integration**: Settings → Integrations → Search "LLM Vision"
- [ ] **Check Version**: Must be v1.4.0+ for timeline card support
- [ ] **Integration Status**: Should show "Configured" (not error state)

### Step 2: Provider Configuration (OpenAI Switch)
- [ ] **Add OpenAI Provider**: Settings → Integrations → LLM Vision → Add Provider
- [ ] **API Key Setup**: Enter valid OpenAI API key from https://platform.openai.com/api-keys
- [ ] **Model Selection**: Use `gpt-4o-mini` (cost-effective for testing)
- [ ] **Test Connectivity**: Provider should show "Connected" status

## Phase 2: Timeline Card Installation Verification

### Step 3: Timeline Card via HACS
- [ ] **Install Card**: HACS → Frontend → Search "LLM Vision Timeline Card"
- [ ] **Repository**: https://github.com/valentinfrlch/llmvision-card
- [ ] **Reload Frontend**: Clear browser cache after installation
- [ ] **Card Availability**: Should appear in "Add Card" options

### Step 4: Timeline Card Configuration
- [ ] **Add to Dashboard**: Edit dashboard → Add Card → Search "LLM Vision Timeline"
- [ ] **Entity Configuration**: `entity: calendar.llm_vision_timeline`
- [ ] **Display Settings**: 
  - `number_of_hours: 24`
  - `number_of_events: 5`
- [ ] **Save Configuration**: Card should appear (may initially show "Off")

## Phase 3: Event Generation and Storage

### Step 5: Manual Event Creation Test
- [ ] **Developer Tools**: Go to Developer Tools → Actions
- [ ] **Find Remember Action**: Search for "llmvision.remember"
- [ ] **Create Test Event**:
  ```yaml
  title: "Manual Test Event"
  summary: "Testing timeline functionality"
  start_time: [current datetime]
  end_time: [current datetime + 5 minutes]
  ```
- [ ] **Execute**: Click "Perform Action"

### Step 6: Verify Event Storage
- [ ] **Check Calendar Entity**: Developer Tools → States → `calendar.llm_vision_timeline`
- [ ] **Verify Events Field**: Should contain test event in events list
- [ ] **Check Timestamps**: Start/end times should match your input
- [ ] **Timeline Card Refresh**: Should now show events (not "Off")

## Phase 4: Automation Integration

### Step 7: Blueprint Automation Setup
- [ ] **Import Blueprint**: Use LLM Vision notification blueprint
- [ ] **Configure Cameras**: Select your cameras (camera.reolink_doorbell, camera.trendnet_ip_572w)
- [ ] **Set Remember: true**: Critical for timeline storage
- [ ] **Provider Selection**: Choose your OpenAI provider
- [ ] **Test Trigger**: Use motion detection or manual trigger

### Step 8: End-to-End Testing
- [ ] **Trigger Motion**: Create motion event on monitored camera
- [ ] **Check Automation**: Verify automation runs without template errors
- [ ] **Monitor Logs**: Developer Tools → System → Logs (search "llmvision")
- [ ] **Verify Timeline**: New event should appear in timeline card
- [ ] **Check Event Quality**: OpenAI should provide better image analysis than Ollama

## Phase 5: Troubleshooting Common Issues

### Issue 1: Timeline Card Shows "Off"
**Root Causes:**
- Timeline card not properly installed via HACS
- Card configuration entity mismatch
- No events stored with `remember: true`
- Frontend cache issues

**Solutions:**
- [ ] Reinstall timeline card via HACS
- [ ] Clear browser cache and reload
- [ ] Verify entity name: `calendar.llm_vision_timeline`
- [ ] Check events exist in calendar entity

### Issue 2: Automation Template Errors
**Common Error**: `'dict object' has no attribute 'entity_id'`
**Solutions:**
- [ ] Check blueprint variable mappings
- [ ] Verify camera entity names are correct
- [ ] Update blueprint to latest version

### Issue 3: Provider Connectivity Issues
**OpenAI Specific:**
- [ ] Verify API key is valid and has credits
- [ ] Check model selection (gpt-4o-mini recommended)
- [ ] Monitor API usage at OpenAI dashboard

## Expected Results After Completion

### Success Criteria:
1. **Timeline Card**: Shows events, not "Off"
2. **Event Quality**: OpenAI provides meaningful descriptions (not "no image data")
3. **Automation**: Runs without errors when motion detected
4. **Storage**: Events persist in calendar.llm_vision_timeline
5. **Real-time Updates**: New events appear in timeline within minutes

### Performance Benchmarks:
- **Response Time**: < 10 seconds for image analysis
- **Event Storage**: Immediate storage in timeline
- **Timeline Display**: Updates within 30 seconds
- **Cost**: ~$0.01-0.05 per image analysis with gpt-4o-mini

This plan eliminates local Ollama variables and provides a systematic approach to verify each component of the LLM Vision timeline functionality.