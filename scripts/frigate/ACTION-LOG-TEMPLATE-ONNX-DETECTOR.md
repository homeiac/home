# Action Log Template: Frigate ONNX GPU Detector Setup

## Execution Date: [DATE]

## Pre-flight Checks
- [ ] Frigate running: `kubectl get pods -n frigate`
- [ ] GPU available: `kubectl exec -n frigate deployment/frigate -- nvidia-smi`
- [ ] Current detector stats: `kubectl exec -n frigate deployment/frigate -- curl -s http://localhost:5000/api/stats | jq '.detectors'`

---

## Step 1: Build ONNX Model
- **Script**: `./build-onnx-k8s-job.sh c 640`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Duration**: [X minutes]
- **Model size**: [X MB]
- **Output**:
```
[paste output here]
```

---

## Step 2: Switch to ONNX Detector
- **Script**: `./19-switch-to-onnx-detector.sh`
- **Status**: [PENDING/SUCCESS/FAILED]
- **Output**:
```
[paste output here]
```

---

## Step 3: Verify Results

### Before Switch
- **CPU usage**: [X]m
- **Inference speed**: [X]ms
- **Detector type**: cpu

### After Switch
- **CPU usage**: [X]m
- **Inference speed**: [X]ms
- **Detector type**: onnx

### Improvement
- **CPU reduction**: [X]%
- **Inference improvement**: [X]%
- **Cores freed**: [X]

---

## Final Status
- **Overall**: [SUCCESS/PARTIAL/FAILED]
- **Notes**:

---

## Rollback (if needed)
```bash
kubectl apply -f k8s/frigate-016/configmap.yaml
kubectl rollout restart deployment/frigate -n frigate
```
- **Executed**: [YES/NO]
- **Reason**:

---

## References
- [Frigate ONNX Docs](https://docs.frigate.video/configuration/object_detectors/#onnx)
- [YOLOv9 Repository](https://github.com/WongKinYiu/yolov9)
- Plan: `/Users/10381054/.claude/plans/wiggly-percolating-sunrise.md`
