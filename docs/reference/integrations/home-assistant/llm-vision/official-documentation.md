# LLM Vision Official Documentation Reference

**Source**: https://llmvision.gitbook.io/getting-started/  
**Saved**: August 2, 2025  
**Purpose**: Local reference to avoid repeated web fetches

## Purpose and Overview

LLM Vision is a Home Assistant integration that uses multimodal Large Language Models (LLMs) to:
- Analyze images, videos, and live camera feeds
- Answer questions about visual content
- Update sensors based on extracted data
- Optionally store analyzed images with AI summaries

## Key Components

1. **Integration** - Core LLM Vision integration providing AI analysis services
2. **Blueprint** (`event_summary`) - Automation template for motion-triggered analysis
3. **Timeline Card** - UI component for viewing analyzed events

## Core Features

- **Stream analysis** - Real-time camera feed analysis
- **Event tracking** - Motion-triggered image analysis with timeline storage
- **Built-in memory** - Recognition of people, pets, or cars across events
- **Multi-provider support** - Works with various AI providers (OpenAI, Ollama, etc.)

## Architecture Highlights

- **Triggered by**: Camera/binary sensor state changes
- **Analysis method**: Uses `stream_analyzer` service to generate summaries
- **Notifications**: Can send notifications via Home Assistant app
- **Storage**: Optional event storage in timeline database
- **Flexibility**: Customizable automation workflows with multiple AI provider options

## Configuration Workflow (Based on Official Docs)

The documentation suggests a flexible setup but doesn't explicitly detail camera/motion sensor mapping workflows in the main overview.

## Services Provided

- `llmvision.image_analyzer` - Analyze static images
- `llmvision.stream_analyzer` - Analyze camera streams/video

## Key Architecture Note

The documentation indicates that LLM Vision is triggered by "camera/binary sensor state changes" but doesn't provide detailed mapping instructions in the main overview. The integration appears to be designed as a service provider that automation blueprints call, rather than handling camera mapping internally.

## Missing Documentation Areas (From User Experience)

Based on real-world usage, the following areas could benefit from clearer documentation:

1. **Camera/Motion Sensor Array Alignment**: How blueprint templates map motion sensors to cameras via index
2. **Blueprint Template Logic**: How the `event_summary` blueprint calculates which camera to analyze
3. **Manual vs Motion Trigger Differences**: Why manual automation triggers bypass camera mapping logic
4. **Configuration Restart Requirements**: When HA restart vs automation reload is needed
5. **Integration vs Automation Configuration**: What's configured in the integration GUI vs automation YAML

## Local Configuration Discoveries

Through real-world debugging, we've determined:
- Camera mapping happens in automation configuration arrays, not integration GUI
- Blueprint template uses index-based mapping: `motion_sensors[i]` → `camera_entities[i]`
- Integration GUI only configures AI providers, not camera mappings
- Manual automation triggers don't test camera mapping logic
- Full HA restart required for new automation input fields

## Reference Files for Complete Setup

- Camera mapping configuration: `docs/reference/integrations/home-assistant/llm-vision/configuration-hints.md`
- Validation protocols: `docs/reference/integrations/home-assistant/validation-protocols.md`
- Troubleshooting guide: `docs/runbooks/llm-vision-camera-mapping-troubleshooting.md`

This local reference avoids repeated web fetches and supplements official documentation with real-world configuration insights.