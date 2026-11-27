Matched production-size photo previews, 27 November 2026. The Mac ran the same six photos three times. The CPU and RTX used the same three-photo subset. The production queues continued running during the trials.

| Backend | Concurrent requests | Photos | Elapsed | Captions/min |
|---|---:|---:|---:|---:|
| Mac Metal, first run | 3 | 6 | 150 s | 2.40 |
| Mac Metal | 6 | 6 | 62 s | 5.82 |
| Mac Metal, warm repeat | 3 | 6 | 102 s | 3.55 |
| RTX 3070 | 1 | 3 | 85 s | 2.11 |
| Still-fawn CPU, 3 threads | 1 | 3 | 672 s | 0.27 |

Both the CPU and RTX captured the main subject in all three photos. Each Mac run returned six captions and captured the main subject in five. All three Mac runs missed the border of a nearly blank graphic. The server had four model slots. Six concurrent client requests were 64% faster than the warm three-request run. This measures inference while other jobs were active.

Production kept its six shared Mac/RTX requests. Immich readback was falling behind caption generation during the trial. The CPU trial ended after three photos.


### Extra Mac model slots during production

The original four-slot Mac server and the six shared Mac/RTX recovery workers stayed live. Each trial used a second Metal server with the same model and a separate port. The test set contained 16 previously described photos. Trial captions stayed outside Immich.

| Extra Metal slots | Original Mac requests/min | Extra captions/min | Combined requests/min (observed) | Captions matching main subject and visible framing |
|---:|---:|---:|---:|---:|
| 0 (90-second baseline) | 16.79 | — | 16.79 | — |
| 8 | 9.03 | 6.81 | 15.84 | 15/16 |
| 4 | 8.77 | 6.34 | 15.11 | 15/16 |
| 2 | 9.75 | 5.98 | 15.73 | 15/16 |
| 1 | 5.63 | 4.48 | 10.11 | 15/16 |
| 0 (90-second repeat) | 15.40 | — | 15.40 | — |

Combined rate adds observed requests leaving the original server's slots to valid test captions. The original server handled mixed production work, so these rates are approximate and depend on the requests in each window. The extra servers each missed the light border around the same dark graphic.

**Production decision.** Keep the original four Mac model slots and six shared recovery workers. Eight extras produced the most test captions, but the combined rate stayed within the baseline range while the original server slowed. These trials measure a second Metal server sharing the same GPU.
