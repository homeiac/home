# Video stories with speech

The output is a useful account of the event: what the camera showed, what was
said, and how the two relate. Speech is evidence, not an instruction to the model.
Do not infer speaker identities from voices or turn spoken claims into verified
visual facts. Keep the original visual caption and timed transcript independently.

1. Continuously discover successful current-version video captions in private
   Parquet. Use the same filename/size presumed-copy grouping as coverage; retain
   a mapping of every member. Never invoke the vision endpoint for this backfill.
2. Extract full mono 16 kHz audio locally. Record no-audio and no-speech outcomes
   explicitly. Whisper uses multilingual detection, timestamps and VAD; failures
   are bounded and isolated, with durable attempts and retry limits.
3. Keep timestamped transcript, model/settings, backend and processing time in a
   separate resumable ledger and Parquet dataset. A single coordinator owns work
   across Mac Metal and RTX CUDA, so no backend can claim the same item twice.
4. Combine only saved visual text, metadata and bounded timed speech into a
   separate audio-aware story. Preserve provenance and expose uncertainty; retain
   visual captions when no reliable speech is available. Refresh the story when
   the visual caption or transcript changes without retranscribing unchanged audio.
5. Measure matched audio on both devices and tune model/decoding/VAD/concurrency.
   Include no-speech and spoken examples. Compare transcript usefulness as well as
   speed. Keep raw audio/transcripts private and publish aggregate evidence only.
6. Show eligible videos, transcribed speech, no-audio/no-speech, failures, stories
   saved, percent complete, throughput, backend timing and queue ETA in Grafana.

Whisper is independent of the existing inline optional faster-whisper helper.
Audio and story workers run through GitOps; native Mac runtime uses launchd and
an AC-only sleep assertion. RTX shares memory with Frigate and Bonsai: keep one
Whisper request, compact weights, and stop RTX admission if headroom is inadequate.
Existing visual processing and reconciliation retain their completed identities.
