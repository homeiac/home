# Home Assistant Interface Reference

## Developer Tools Structure
Based on official Home Assistant documentation (https://www.home-assistant.io/docs/tools/dev-tools/)

### Available Tabs:
1. **YAML** - Configuration validation and reloading specific sections
2. **States** - View all entities, states, and attributes; temporarily update states for testing
3. **Actions** - Execute actions from integrations (formerly called "Services")
4. **Template Editor** - Test Jinja2 templates with real-time preview
5. **Events** - Fire custom events and subscribe to event types
6. **Statistics** - Manage long-term statistics and correct measurement data
7. **Assist** - Test voice command processing and intent matching

### Key Points:
- Actions tab is the correct location for executing integration actions
- Actions are dynamically populated based on installed integrations
- Action data is passed in YAML format
- **Button terminology**: "Perform Action" (not "Call Service")
- Interface is designed for all users, not just developers

### Common Integration Patterns:
- Integration actions follow pattern: `integration_name.action_name`
- Search functionality available in Actions tab
- Actions require proper YAML formatting for parameters
- Execute actions using "Perform Action" button

## LLM Vision Integration Specifics

### LLM Vision Actions Available:
- `llmvision.image_analyzer` - Analyze single or multiple images
- `llmvision.video_analyzer` - Analyze video files  
- `llmvision.stream_analyzer` - Analyze live camera streams
- `llmvision.data_analyzer` - Extract structured data from images
- `llmvision.remember` - Create custom timeline events

### Developer Tools Usage for LLM Vision:
- **Actions Tab**: Execute LLM Vision services with YAML parameters
- **States Tab**: Check `calendar.llm_vision_timeline` entity for stored events
- **Button**: "Perform Action" (not "Call Service")

This reference prevents assumptions about Home Assistant interface structure and ensures accurate guidance.