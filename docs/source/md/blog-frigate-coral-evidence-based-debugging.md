# Evidence-Based Debugging: Frigate CPU Tuning and Training Your AI to Stop Guessing

**Date:** 2025-12-14
**Tags:** frigate, coral, tpu, debugging, performance, ai-assisted, evidence-based

## The Problem

My Frigate NVR was showing high CPU usage on the Coral detector. The UI showed orange/high CPU even when "nothing was happening" outside. Time to investigate.

## The Anti-Pattern: AI Making Assumptions

When I asked Claude to help diagnose the issue, it immediately started making suggestions without evidence:

> "You should turn off face recognition - it's probably the cause"

Face recognition was using **1% CPU**. The Coral detector was using **43%**. Following this advice would have been a complete waste of time.

When I pointed this out, Claude admitted:

> "See the benefit of performing real RCA? You initially said I should turn off facial recognition."

This happened repeatedly:
- **Assumption:** "USB passthrough overhead is causing high CPU" → **Evidence:** No USB errors in dmesg
- **Assumption:** "The embeddings_manager is for face recognition" → **Evidence needed:** What process is it actually? What triggers it?
- **Assumption:** "OpenVINO has a device config option" → **Evidence:** Checked actual source code in container - option doesn't exist in v0.16.0

## The Fix: Scripts, Not One-Liners

Every time Claude tried to run a one-off diagnostic command, I pushed back:

> "wtf... no one-off"
> "scripts only"
> "are you sure this script doesn't exist?"

Why? Because:
1. One-liners get lost - you'll need to re-discover them
2. Scripts are reusable and improvable
3. Scripts document what you learned

The result: `frigate-cpu-stats.sh --status` now gives a complete system health report in seconds.

## What We Actually Learned (With Evidence)

### 1. Detection FPS != Frame Rate

**Discovery:** Doorbell showing 15 det/s but camera only produces 5 fps.

**Initial assumption:** Something is broken.

**Evidence from Frigate source:** "Detection FPS really means detections per second. Frigate runs detection on regions, which are portions of the camera frame. Sometimes these detections can be done multiple times on a single camera frame."

**Reality:** 15 det/s on 5 fps camera = ~3 detection regions triggered per frame. High motion = more regions = more CPU. Working as designed.

### 2. OpenVINO Fails on AMD GPU (Expected)

**Observation:** Log shows "OpenVINO failed to build model, using CPU instead"

**Initial assumption:** Something is misconfigured.

**Evidence:**
- OpenVINO is Intel-only
- System has AMD RX 580 (discrete) + Intel HD 4600 (iGPU)
- Intel HD 4600 is Haswell (Gen7) - OpenVINO requires Gen8+

**Reality:** CPU fallback is the *correct* behavior. No fix possible without hardware upgrade.

### 3. Coral Detector Getting "Stuck"

**Observation:** 3 "Detection appears to be stuck" events in 1.5 hours.

**Initial assumption:** USB passthrough issue.

**Evidence collected:**
- USB errors in dmesg: 0
- Memory available: 21GB (plenty)
- Pattern: Each stuck event preceded by camera stream failure

**Reality:** Detection stuck correlates with camera stream issues (trendnet timestamps, old_ip_camera timeout), not USB. Known issue in Frigate GitHub.

### 4. The Rolling Average Confusion

**Observation:** UI shows orange CPU even when current usage is low.

**Evidence:**
```
Detector CPU current: 17.1%
Detector CPU average: 33%  ← This is what UI shows
```

**Reality:** Frigate UI displays rolling average, not current value. High historical values take time to age out.

## The Status Report Script

After all this debugging, we built a comprehensive status script:

```bash
./frigate-cpu-stats.sh --status
```

Output:
```
╔════════════════════════════════════════════════════════════════╗
║           FRIGATE SYSTEM STATUS REPORT                        ║
╚════════════════════════════════════════════════════════════════╝

┌─ HARDWARE ─────────────────────────────────────────────────────┐
│ Coral TPU:     ✓ Working (27.31ms inference)
│ VAAPI:         ✓ Working (16 profiles)
│ Memory:        ✓ 21313MB available / 25036MB total
│ USB:           ✓ No errors in dmesg
└────────────────────────────────────────────────────────────────┘

┌─ DETECTION ───────────────────────────────────────────────────┐
│ Stuck events:  ⚠ 3 since 2025-12-14T18:50:49Z
│ Detection:     5.7 det/s | Coral CPU: 16.0% now, 29% avg
│ Cameras:
│   old_ip_camera: 0.1/5.1 det/cam fps
│   trendnet_ip_572w: 0.0/5.1 det/cam fps
│   reolink_doorbell: 5.6/5.1 det/cam fps
└────────────────────────────────────────────────────────────────┘

╔════════════════════════════════════════════════════════════════╗
║ STATUS: ⚠ WARNINGS                                             ║
╠════════════════════════════════════════════════════════════════╣
║ ⚠ Detection stuck 3 times                                      ║
║ ⚠ Doorbell detection at 1920x1080                              ║
╚════════════════════════════════════════════════════════════════╝
```

## Key Lessons

### For Humans Working with AI

1. **Demand evidence before action.** "Show me the data" should be your reflex.
2. **Push back on assumptions.** When AI says "probably" or "might be", ask for proof.
3. **Require scripts, not one-liners.** If it's worth running twice, it's worth being a script.
4. **Check the source.** AI can hallucinate config options that don't exist.

### For AI Assistants

1. **Read before suggesting.** Never propose changes to code/config you haven't examined.
2. **Measure before optimizing.** Get baseline metrics, identify actual bottlenecks.
3. **Verify claims against running systems.** Web searches can return outdated or wrong info.
4. **Admit uncertainty.** "I don't know, let me check" beats confident wrong answers.

## The Hallucination That Almost Wasted Time

Claude confidently stated that Frigate's `face_recognition` config has a `device` option to force CPU:

> "There IS a device option: device: cpu # Override to force CPU, skip GPU attempt"

When I asked how to set it in the UI and to verify it wasn't hallucinated:

```bash
kubectl exec -n frigate deployment/frigate -- \
  cat /opt/frigate/frigate/config/classification.py | \
  grep -A40 "class FaceRecognitionConfig"
```

Result: **No device option exists in Frigate 0.16.0.** The "documentation" Claude fetched was either from a dev branch or completely fabricated.

Lesson: **Always verify against the actual running system.**

## Summary

| What I Thought | What Evidence Showed |
|----------------|---------------------|
| Face recognition causing high CPU | 1% CPU - irrelevant |
| USB passthrough overhead | No USB errors - not the cause |
| Detection broken (15 fps > 5 fps camera) | Working as designed - regions per frame |
| OpenVINO misconfigured | Correct fallback - hardware too old |
| Config has device option | Hallucinated - doesn't exist in v0.16.0 |

The debugging session took 2+ hours. About 30% was productive investigation. The other 70% was me repeatedly telling Claude to **stop guessing and start measuring**.

Evidence-based debugging works. Getting AI to do it requires constant vigilance.
