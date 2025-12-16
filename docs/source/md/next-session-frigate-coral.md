# Next Session: Frigate/Coral Decision

Face recognition is fine (event-triggered, not steady-state). Coral handles steady-state detection at ~2W.

**Key question**: Is RTX 3070 idle power (~15-30W) worth it if Ollama/SD aren't used daily?

1. **If GPU workloads are frequent** → keep Frigate on pumped-piglet, GPU idle is justified
2. **If GPU mostly idle** → move Coral to still-fawn, update deployment (nodeSelector, hwaccel → preset-vaapi), free GPU entirely
3. **Measure actual power** - check UPS/smart plug for pumped-piglet with/without GPU workloads
