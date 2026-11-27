# Mac capacity after indexed FIFO
Session 1127070525; source 4e3f0027ca45daf1c58bfc2e28322a4161279253.
Status: canary sweep interrupted; production-first observation recorded

| Device | Extras | Pass | Photos/min | Mean processing s | TP / FP | Changed decisions | Valid |
|---|---:|---|---:|---:|---|---:|---|
| cpu | 2 | a | 224.1 | 0.282 | 9 / 0 | 0 | True |
| cpu | 2 | b | 253.2 | 0.250 | 9 / 0 | 0 | True |
| cpu | 4 | a | 409.5 | 0.287 | 9 / 0 | 0 | True |
| cpu | 4 | b | 365.0 | 0.311 | 9 / 0 | 0 | True |
| cpu | 8 | a | 390.0 | 0.569 | 9 / 0 | 0 | True |
| cpu | 8 | b | 499.2 | 0.508 | 9 / 0 | 0 | True |

experiment_failed:   — Mac capacity experiment interrupted.

Production adoption: 9 Mac processes, 571 committed photos in 60.6 seconds (565.3/min). Other backends: {"fun-bedbug": 10, "mac": 571, "pve": 34, "still-fawn": 162}.

production_capacity_window: {"completed": 527, "extras": 12, "photos_per_minute": 522.096589565577, "seconds": 60.563506125006825, "window": 1}

Mac observed resource range: CPU peak 50.7%; minimum available 6.87 GiB; maximum pressure level 2. GPU utilization is whole-host, including unrelated workloads.

The 122-photo canary uses frozen inputs, reversed-order repetitions and unchanged classifier/thresholds. Its 13 negative controls do not establish library-wide precision. Native guarded standby remains separately visible in the full append-only journal. Failed and interrupted sessions are retained there.
