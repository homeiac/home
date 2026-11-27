Matched production-size photo previews, 27 November 2026. The Mac ran the same six photos three times. The CPU and RTX used the same three-photo subset. The production queues continued running during the trials.

| Backend | Concurrent requests | Photos | Elapsed | Captions/min |
|---|---:|---:|---:|---:|
| Mac Metal, first run | 3 | 6 | 150 s | 2.40 |
| Mac Metal | 6 | 6 | 62 s | 5.82 |
| Mac Metal, warm repeat | 3 | 6 | 102 s | 3.55 |
| RTX 3070 | 1 | 3 | 85 s | 2.11 |
| Still-fawn CPU, 3 threads | 1 | 3 | 672 s | 0.27 |

Both the CPU and RTX captured the main subject in all three photos. Each Mac run returned six captions and captured the main subject in five. All three Mac runs missed the border of a nearly blank graphic. Six concurrent requests were 64% faster than the warm three-request run. This measures inference while other jobs were active.

Production kept its six shared Mac/RTX requests. Immich readback was falling behind caption generation during the trial. The CPU trial ended after three photos.
