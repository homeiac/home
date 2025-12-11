# The Case of the Phantom Load: A Homelab Mystery

*How a wise mentor's pointed questions unraveled a cascade of infrastructure failures*

---

It started, as these things often do, with a simple observation.

"Why is fun-bedbug busy?"

The question hung in the air. I dove in confidently, SSH keys at the ready, certain I would find the culprit in seconds. Load average 4.62 on a 2-core AMD A9-9400. Frigate had just restarted and was initializing. Case closed, right?

*Wrong.*

## The First Misdirection

I explained, with perhaps too much confidence, that Frigate's startup was CPU-intensive. The embeddings manager was churning. The weak hardware was simply overwhelmed. "Give it a few minutes," I said. "The load will settle."

We stopped Frigate. We removed the container entirely. The system had migrated to still-fawn anyway - this was just cleanup.

I watched the numbers. Load average 3.61... dropping. Victory was at hand.

Or so I thought.

## "Still the same"

Three words. Three words that shattered my neat explanation.

The Grafana dashboard told a different story than my optimistic predictions. CPU Busy: 100%. Sys Load: 168.5%. The gauges glowed an angry red, mocking my earlier assurances.

"You're impatient," I countered, pointing to the graph. "Look - it's dropping. The load average is a rolling metric. Give it time."

But the mentor knew better. He waited. He watched. And then:

"Still the same."

## The Phantom Appears

Something was deeply wrong. I went back in, this time with different tools. Not `top`. Not `ps`. I needed to see what the system was *waiting* for.

```
vmstat 1 3
```

The output made my blood run cold:

```
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 1  3 1069824 ...                                                        0 95  0
```

**95% I/O wait.** Three processes blocked. The CPU wasn't busy computing - it was *waiting*. Waiting for something that would never come.

I searched for processes in the dreaded D state - uninterruptible sleep, the zombie's crueler cousin. And there it was:

```
root  2360161  0.0  0.4 372272 35584 ?  Ds  Dec10  0:00 task UPID:fun-bedbug:00240361:...vzdump...
```

A backup job. Started December 10th. Still "running." Frozen in time, clutching at a disk that no longer existed.

## "There was no manual one"

I made a mistake then. I assumed. I speculated. "It was likely a manual backup," I said, trying to fill in the gaps with plausible fiction.

The response was swift and surgical: "When you say 'likely' then it is probably wrong."

A lesson delivered with the precision of a master teaching an overconfident apprentice. Don't guess. *Know.*

## The Real Story Emerges

I traced the actual cause. The scheduled backup job - `backup-ff3d789f-f52b` - ran every day at 2:30 and 22:30. It backed up *all* containers except one. And containers 106 and 113? They had mount points configured:

```
mp0: local-3TB-backup:subvol-113-disk-0,mp=/media,backup=1
```

That `backup=1` flag. The backup job dutifully tried to include this mount point. But `local-3TB-backup` was a ZFS pool on a 3TB USB drive that had been physically moved to still-fawn. The pool was gone. The mount was gone. But the configuration remained, pointing to a ghost.

When vzdump tried to read from that path, the I/O request went into the void. The kernel waited. And waited. The process entered D state - unkillable, uninterruptible, undead.

Every 12 hours, another backup would try. Another process would join the horde.

## The Exorcism

The fix required surgery on multiple files:

1. **`/etc/vzdump.conf`** - Still pointed to `/local-3TB-backup/backup-tmpdir`. Removed.

2. **`/etc/pve/storage.cfg`** - The storage definition claimed the 3TB pool belonged to fun-bedbug. It didn't anymore. Removed, then re-added with `nodes still-fawn`.

3. **LXC 106 and 113 configs** - Both had mount points to the phantom storage. These containers weren't even needed anymore - Frigate had moved. The mount points were excised.

4. **The stuck process itself** - D state processes cannot be killed. They exist in kernel space, waiting for I/O that will never complete. Only a reboot could release its grip.

```bash
ssh root@fun-bedbug.maas "reboot"
```

## The Aftermath

When fun-bedbug came back online, the load average was under 1.0. The angry red gauges faded to peaceful green. The phantom was gone.

But more importantly, the *cause* was gone. The next scheduled backup at 22:30 would run cleanly, no longer reaching for storage that existed only in configuration files.

## Lessons from the Master

What did I learn from this investigation?

1. **Symptoms lie.** High CPU looked like Frigate's fault. It wasn't. Always dig deeper.

2. **"Likely" is lazy.** When you speculate instead of investigate, you build castles on sand. The mentor's correction - "when you say likely then it is probably wrong" - should be tattooed on every SRE's forearm.

3. **Ghost configurations haunt.** When you move hardware, every reference to that hardware becomes a landmine. Storage configs, mount points, backup jobs - they all remember what was, not what is.

4. **D state is death.** A process in uninterruptible sleep is a symptom of I/O trying to reach something unreachable. Find what's missing.

5. **The wise ask simple questions.** "Why is it busy?" "Still the same." "There was no manual one." Each question was a scalpel, cutting away my assumptions until only truth remained.

---

*The homelab runs quietly now. fun-bedbug hums along at load average 0.8, its phantom exorcised, its configurations cleansed. Somewhere, a 3TB USB drive sits contentedly in still-fawn, unaware of the chaos its migration caused.*

*And the mentor? He simply nodded and moved on to the next question. As they do.*

---

**Tags:** homelab, proxmox, debugging, zfs, vzdump, sysload, linux, infrastructure, troubleshooting, proxmocks, sysadmin, load-average, io-wait

**Related:** [Frigate Migration Guide](/docs/frigate-migration), [ZFS Storage Management](/docs/zfs-storage), [Proxmox Backup Configuration](/docs/proxmox-backup)
