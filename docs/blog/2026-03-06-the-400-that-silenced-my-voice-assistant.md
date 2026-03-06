# The 400 That Silenced My Voice Assistant

*2026-03-06*

"OK Nabu, what's my notification?"

Blue light. The Voice PE heard me. It even knew I had a notification — a package had arrived, and the blue light was already on. It understood my words, sent them to Home Assistant, which sent them to Ollama, and... nothing. No response. Just blue, pulsing, forever.

This is the third time in three months that the same symptom — blue LED, no voice — has had a completely different root cause. In January it was a `setup_error`. In February it was VRAM overflow. This time, it was a single boolean.

## The Debugging

Ollama was running. The pod was healthy. I could curl it directly and get a perfect response:

```bash
curl http://192.168.4.85/api/chat -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"hello"}],"stream":false}'
# "Hello! How can I assist you today?"
```

But the Ollama logs told a different story:

```
18:09:31 | 400 | 44ms | 10.42.0.1 | POST /api/chat
18:48:06 | 400 | 48ms | 10.42.0.1 | POST /api/chat
```

Every request from Home Assistant was getting rejected with a 400. My direct curl got 200. Same endpoint, same model, different result. The difference had to be in the request body.

## 44 Milliseconds

That 44ms response time was the clue. A model that's not found returns an error in ~40ms too, but with a proper message. A model that needs to load takes 10+ seconds. A model that's thinking takes minutes. But 44ms for a 400 means Ollama rejected the request at the validation layer — before it even touched the model.

I started testing every parameter combination. Tools? Fine. System messages? Fine. Options? Fine. Then:

```bash
curl http://192.168.4.85/api/chat -d '{"model":"qwen2.5:7b",...,"think":true}'
# {"error": "\"qwen2.5:7b\" does not support thinking"}
# HTTP 400
```

There it is.

## The Think Toggle

Ollama 0.17 added a `think` parameter for reasoning models — the ones that show their work before answering. Home Assistant's Ollama integration has a matching toggle: "Think before responding." Somewhere along the way, I'd flipped it on. The default is off.

The problem: `qwen2.5:7b` is not a reasoning model. It doesn't support thinking. So every single voice request was:

1. Voice PE sends audio to HA
2. HA transcribes speech to text
3. HA sends text to Ollama with `think: true`
4. Ollama rejects it: 400
5. HA gets an error, Voice PE gets nothing
6. Blue light pulses until heat death of the universe

No error in the HA logs. No notification. No UI indication. The voice assistant just silently stopped working.

## The Fix (The GitOps Way)

Two changes, one commit:

**Upgrade Ollama**: `0.17.0` → `0.17.7`. Not strictly necessary for the fix, but required for what comes next.

**Switch to qwen3.5:4b**: The Qwen 3.5 family supports thinking natively. At 3.4 GB, it fits comfortably in the RTX 3070's 8 GB VRAM. It's also newer, faster, and multimodal — all of which are irrelevant for "what's my notification" but nice to have.

```yaml
# deployment.yaml
- image: ollama/ollama:0.17.0
+ image: ollama/ollama:0.17.7

# job-model-update.yaml
- value: "qwen3:4b"
+ value: "qwen3.5:4b"
```

Push. Flux reconciles. New pod comes up. Model pulls. Old models deleted. Update HA to use `qwen3.5:4b`. Test:

```
Thinking: "Analyze the Request: The user is asking a simple arithmetic question..."
Response: "The answer to 2 + 2 is 4."
Done: true
```

"OK Nabu, what's my notification?"

"You have a package delivery notification."

Two seconds. With thinking.

## The Pattern

Three incidents, three root causes, one symptom:

| Date | Root Cause | Failure Mode |
|------|-----------|--------------|
| January | `setup_error` — HA gave up connecting | Integration permanently surrendered |
| February | VRAM overflow — model too big for GPU | 1 token/sec, 100-second responses |
| March | `think: true` on non-thinking model | 400 rejected, zero response |

The voice pipeline is four components deep: hardware satellite, speech processing, conversation agent integration, and LLM inference. Each component fails silently in its own special way. The satellite shows blue regardless of whether the backend is thinking, broken, or on fire. HA doesn't surface Ollama 400s anywhere visible. Ollama doesn't warn you when you load a model that can't do what the client is asking.

## What I Actually Learned

The 44ms was the whole investigation. Every other signal — NotReady nodes, stale kubeconfigs, guest agents down — was noise. The pod was running. The API was responding. The model was loaded. The only thing wrong was a parameter that shouldn't have been there, rejected in less time than it takes to blink.

For infrastructure people, there's a lesson: when the error is fast, it's a validation problem. When it's slow, it's a resource problem. When there's no error at all, it's a configuration problem. This was all three, but the one that mattered was the fast one.

For anyone running a local voice assistant: check your model's capabilities before enabling features. And maybe keep a direct curl command handy. The voice pipeline has a lot of opinions about what went wrong, but Ollama's HTTP status code doesn't lie.

**RCA**: `docs/rca/2026-03-06-voice-pe-ollama-think-400.md`
**Commit**: `4fec36f`
