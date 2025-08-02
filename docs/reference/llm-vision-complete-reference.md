# LLM Vision Complete Reference Guide

*Based on systematic review of official documentation: https://llmvision.gitbook.io/getting-started*

## Installation Requirements

### Prerequisites:
- Home Assistant with HACS installed
- Camera entities configured in Home Assistant
- AI provider (OpenAI, Ollama, etc.)

### Installation Process:
1. **HACS Installation**: Click HACS repository button → Follow HACS instructions
2. **Restart Required**: Restart Home Assistant after installation
3. **Integration Setup**: Settings → Devices & Services → Add Integration → "LLM Vision"
4. **Version Compatibility**: Keep Integration, Timeline Card, and Blueprint at matching versions

## Provider Configuration

### OpenAI Setup:
- **API Key**: Obtain from https://platform.openai.com/api-keys
- **Credits Required**: Must add credits before making requests
- **Recommended Models**:
  - `gpt-4o`: Fast, intelligent, flexible (higher cost)
  - `gpt-4o-mini`: Fast, affordable, focused tasks (lower cost)
- **Pricing**: Use calculator at https://openai.com/api/pricing

### Ollama Setup (Kubernetes-Based):

#### **Kubernetes Deployment with Persistent Models**
*For homelab K3s clusters with GPU passthrough*

**Step 1: Create Ollama Namespace and PVC**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ollama-system
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-models-pvc
  namespace: ollama-system
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi  # Adjust based on models needed
  storageClass: local-path  # Or your preferred storage class
```

**Step 2: Deploy Ollama with GPU Support**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: ollama-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      nodeSelector:
        kubernetes.io/hostname: still-fawn  # Your GPU node
      containers:
      - name: ollama
        image: ollama/ollama:latest
        ports:
        - containerPort: 11434
        env:
        - name: OLLAMA_HOST
          value: "0.0.0.0"
        - name: OLLAMA_KEEP_ALIVE
          value: "-1"  # Keep models loaded in GPU memory
        volumeMounts:
        - name: ollama-storage
          mountPath: /root/.ollama
        resources:
          requests:
            nvidia.com/gpu: 1
            memory: "4Gi"
            cpu: "2000m"
          limits:
            nvidia.com/gpu: 1
            memory: "16Gi"
            cpu: "8000m"
      volumes:
      - name: ollama-storage
        persistentVolumeClaim:
          claimName: ollama-models-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: ollama-service
  namespace: ollama-system
spec:
  type: LoadBalancer  # Or ClusterIP if using Traefik
  ports:
  - port: 11434
    targetPort: 11434
  selector:
    app: ollama
```

**Step 3: Load Vision Model (Gemma2 Vision)**
```bash
# Once Ollama pod is running, exec into it to pull model
kubectl exec -it deployment/ollama -n ollama-system -- ollama pull gemma2-vision:latest

# Verify model is loaded
kubectl exec -it deployment/ollama -n ollama-system -- ollama list
```

**Step 4: DNS Configuration**
- **OPNsense Unbound DNS Override**: `ollama.app.homelab` → `192.168.4.80` (Traefik)
- **Home Assistant Configuration**: Use `http://ollama.app.homelab`
- **Alternative Direct Access**: `http://192.168.4.81` (direct LoadBalancer IP)

**Verification Steps:**
1. **Pod Status**: `kubectl get pods -n ollama-system` shows Running
2. **GPU Allocation**: `kubectl describe pod -n ollama-system` shows GPU assigned
3. **Model Loaded**: `kubectl exec -it deployment/ollama -n ollama-system -- ollama list` shows gemma2-vision
4. **Network Access**: `curl http://ollama.homelab:11434/api/tags` returns model list
5. **Home Assistant Test**: LLM Vision provider connects successfully

## Core Actions Reference

### `llmvision.image_analyzer`
**Purpose**: Analyze single or multiple images
**Required Parameters**:
- `provider`: AI provider configuration ID
- `message`: Prompt to send with image(s)

**Optional Parameters**:
- `image_file` or `image_entity`: Specify image source
- `max_tokens`: Response length limit (default: 100)
- `target_width`: Downscaling width (default: 1280)
- `temperature`: Response creativity (0.0-1.0)
- `include_filename`: Include filename in analysis
- `remember`: Store event in timeline (true/false)

### `llmvision.remember`  
**Purpose**: Create custom timeline events
**Required Parameters**:
- `title`: Event title
- `summary`: Event description

**Optional Parameters**:
- `image_path`: Image file path (starts with `/config/www/llmvision/`)
- `camera_entity`: Associated camera
- `start_time`: Event start (defaults to now)
- `end_time`: Event end (defaults to start_time + 1 minute)

## Timeline Card Configuration

### Installation:
- **Repository**: https://github.com/valentinfrlch/llmvision-card
- **Method**: Install via HACS Frontend section
- **Requirements**: LLM Vision v1.4.0+

### Configuration Options:
```yaml
type: custom:llmvision-timeline-card
entity: calendar.llm_vision_timeline  # Required
number_of_hours: 24                   # Show events from past X hours
number_of_events: 5                   # Max events to display (max: 10)
category_filters: []                  # Filter by categories
custom_colors: []                     # Custom RGB colors
language: en                          # UI language
```

### Entity Structure:
- **Entity ID**: `calendar.llm_vision_timeline`
- **Entity Type**: Calendar (not sensor)
- **Attributes**:
  - `events`: Comma-separated event titles
  - `starts`: Comma-separated start timestamps
  - `ends`: Comma-separated end timestamps  
  - `summaries`: Comma-separated event descriptions
  - `key_frames`: Comma-separated image file paths
  - `camera_names`: Comma-separated camera entities

## Settings Configuration

### Available Settings:
1. **Fallback Provider**: Automatic retry with backup provider
2. **System Prompts**: Customize AI behavior and responses
3. **Timeline**: Event tracking and display
4. **Memory (Beta)**: Store reference images for context

### Access Settings:
- Path: LLM Vision Settings → ... → Reconfigure

## Common Issues & Solutions

### Timeline Card Shows "Off":
**Possible Causes**:
1. Timeline card not properly installed via HACS
2. No events stored with `remember: true`
3. Entity configuration mismatch
4. Frontend cache issues

**Diagnostic Steps**:
1. Check `calendar.llm_vision_timeline` exists in Developer Tools → States
2. Verify events are stored in entity attributes
3. Confirm timeline card entity configuration matches
4. Clear browser cache and reload

### Provider Connectivity Issues:
**OpenAI**:
- Verify API key validity
- Confirm account has credits
- Check model availability

**Ollama (Kubernetes)**:
- Pod status: `kubectl get pods -n ollama-system`
- Service accessibility: `kubectl get svc -n ollama-system`
- Model availability: `kubectl exec -it deployment/ollama -n ollama-system -- ollama list`
- DNS resolution: `nslookup ollama.homelab`
- API test: `curl http://ollama.homelab:11434/api/tags`

### Image Analysis Returns "No Image Data":
**Common Causes**:
- Camera entity not accessible
- Image file path incorrect
- Provider not receiving image properly
- Model not vision-capable

**Solutions**:
- Test with manual image_entity specification
- Verify camera entity exists and provides images
- Switch to known working provider for testing
- Confirm model supports vision: `kubectl exec -it deployment/ollama -n ollama-system -- ollama show gemma2-vision`

## Integration Success Verification

### Step-by-Step Verification:
1. **Integration Status**: Settings → Integrations → LLM Vision shows "Configured"
2. **Provider Test**: Developer Tools → Actions → `llmvision.image_analyzer` with manual parameters
3. **Calendar Entity**: Developer Tools → States → `calendar.llm_vision_timeline` shows recent events
4. **Timeline Card**: Dashboard shows events with timestamps (not "Off")
5. **Automation**: Blueprint automation runs without template errors

### Success Indicators:
✅ Timeline card displays events with meaningful descriptions
✅ Manual `llmvision.remember` creates visible timeline entries  
✅ Camera motion triggers automatic event creation
✅ AI provides relevant image analysis (not generic error messages)
✅ Events persist in calendar entity between Home Assistant restarts
✅ Kubernetes Ollama pod maintains model loaded in GPU memory

This reference provides systematic approach to LLM Vision integration with Kubernetes-based Ollama deployment.