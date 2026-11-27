| Capture | Backend | Processing s | Completion interval s | Estimated residual s |
|---|---|---:|---:|---:|
| before-fifo | fun-bedbug | 4.9389 | 6.8463 | 1.9074 |
| before-fifo | mac | 0.3779 | 2.5981 | 2.2202 |
| before-fifo | pve | 1.6249 | 3.1914 | 1.5665 |
| before-fifo | still-fawn | 0.6792 | 2.7860 | 2.1069 |
| after-fifo-stable | fun-bedbug | 5.2446 | 5.5402 | 0.2956 |
| after-fifo-stable | mac | 0.4493 | 0.7242 | 0.2748 |
| after-fifo-stable | pve | 1.7209 | 1.9062 | 0.1853 |
| after-fifo-stable | still-fawn | 0.8195 | 0.9479 | 0.1284 |

| Capture | Backend | Committed photos/min over three minutes |
|---|---|---:|
| before-fifo | fun-bedbug | 9.0 |
| before-fifo | mac | 68.0 |
| before-fifo | pve | 18.7 |
| before-fifo | still-fawn | 61.7 |
| after-fifo-stable | fun-bedbug | 9.0 |
| after-fifo-stable | mac | 250.7 |
| after-fifo-stable | pve | 30.3 |
| after-fifo-stable | still-fawn | 144.0 |

before-fifo candidate timings: mac-base=1661.587 ms (1 rows), mac-burst=1600.194 ms (1 rows)

after-fifo-stable candidate timings: ready=0.286 ms (1 rows)

- Candidate timing is a SELECT without row locks/UPDATE; it is not total claim latency.
- Processing includes download and inference, but excludes claim and completion acknowledgement.
- Completion intervals include the independent Immich writer. Residual is estimated pipeline overhead, not measured network time.
- Three-minute production windows contain different photos; they are not matched hardware benchmarks.
- Network probe measures a small control GET, not photo download bandwidth or claim latency.
