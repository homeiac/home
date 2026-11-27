# Seven residual media failures: source validation and bounded recovery

Issue #244. This follows the 3,178-asset preview recovery, which completed 3,171
assets and left seven failed records. The objective was to recover usable media
without fabricating pixels, weakening recognition thresholds, broadening the
persistent tagger credential, or replacing original files.

## Findings

Six assets had exhausted four attempts with `thumbnail_http_422`. Their playback
requests returned HTTP 200, but both downloaded content and the stored files
failed FFmpeg/ffprobe. These were generated motion-photo companions under
Immich's encoded-video storage, each linked to a still image. The files lacked
valid MP4 container structure; this was not a network transfer failure.

Two linked originals contained actual MP4 streams at different byte offsets.
Extracting at the verified MP4 container boundaries produced clips of 3,567,906
and 2,744,523 bytes. Both passed full video-frame decoding. An initial null-muxer
check reported duplicate presentation timestamps; a timestamp-free raw-frame
sink distinguished muxer warnings from decoder errors. First frames were decoded
with the normal resize policy and visually reviewed. Both depicted non-dog
content. The other four linked stills decoded normally but contained no
recognizable embedded MP4 stream. Their invalid companions cannot be reconstructed
from the bytes inspected.

The pinned [Immich metadata extractor](https://github.com/immich-app/immich/blob/v3.4.2/server/src/services/metadata.service.ts)
uses motion-photo length/offset metadata to extract a byte range. The findings
are consistent with stale offsets or retained motion metadata after image edits;
that causal history is an inference, not a directly observed editing event.

One PNG had `thumbnail_http_403`: its preview was absent and the tagger credential
could not download originals. Read-only inspection through the existing server
mount revealed a second, deeper issue: the PNG header/dimensions were valid, but
full decoding failed. A tolerant decode produced a mostly black, visibly broken
image and was rejected for classification. Of 160 located IDAT chunks, 159 had
valid checksums; chunk framing included displaced 603-byte regions, and the
compressed pixel stream did not validate. A bounded fragment reconstruction was
attempted but found no unique CRC-verified solution. No candidate was accepted.

## Recovery and outcome

The two embedded-video frames were already present in the decoder cache, with
source provenance `live_photo_embedded_video` and `embedded_video`. The installer
initially refused to overwrite those different encodings. They were then compared
visually against independently recovered frames and verified by exact cached
hash before reuse. No cache frame or original media file was overwritten.

Run `waffles-motion-recovery-20261127` retried only those two assets. Both completed
(one on Mac, one on fun-bedbug), with zero Waffles matches and zero new assignments.
The earlier seven failures remain in their original run as historical evidence;
a cross-run report shows **five unresolved assets**, not seven current unresolved
assets. Across the original 78,900-asset inventory, 78,895 now have completed
classification results through these runs.

The read-only source search examined 243,088 library files and 6,753 preserved
version files. It found no alternate intact copy for the unresolved media. The
source dataset had no existing ZFS snapshots to inspect. This does not prove that
no intact copy exists elsewhere, such as an original export or device backup.
An intact source is still needed for further recovery of those five assets.

A transient Kubernetes readiness failure interrupted the first database backup;
no repair was submitted during that outage. Readiness recovered and a subsequent
565,982,036-byte Immich database archive was fully verified. Local DNS resolution
also failed temporarily; the version search used the inventoried host address
while retaining hostname-based SSH key verification. No VM was stopped or disk
mounted for this investigation.

## Reproduction and validation

Private identifiers, originals, frames, plans, hashes and detailed diagnostics are
kept in the private `residual-recovery-20261127` evidence directory, outside Git.
The repository scripts accept that directory and print aggregate diagnostics:

- `inspect-media-failures.py`, `diagnose-media-decode.py`, and
  `inspect-original-media.py`: distinguish request failures from source decoding.
- `inspect-motion-parents.py`, `probe-motion-sources.py`, and
  `prepare-motion-repair.py`: find linked stills and validate embedded streams.
- `inspect-recovery-cache.py` and `seed-recovered-frames.py`: refuse blind cache
  replacement, then reuse hash-verified frames and submit a separate retry run.
- `diagnose-failed-png.py`, `audit-png-chunks.py`, and
  `repair-png-fragments.py`: distinguish superficial header validity from complete
  image integrity; reconstruction requires every chunk CRC, the zlib checksum and
  the complete expected RGBA pixel count.
- `find-source-copies.py`, `find-version-copies.py`, and
  `find-png-snapshot-copy.py`: bounded read-only source-copy checks.
- `report-residual-recovery.py`: report final retries and unresolved cross-run count.
- `wait-api-ready.py`: bounded readiness wait with visible progress.

Three PNG reconstruction tests pass: a synthetic displaced fragment is restored
byte-for-byte, unverified corruption is rejected, and non-PNG input is rejected.
The actual damaged PNG failed the integrity gate, as required. Original source
files, recognition thresholds, and baseline worker counts remain unchanged.
