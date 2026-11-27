# Immich albums on Google Wi-Fi

## Desired behavior

Phones and laptops on the normal Google Wi-Fi network open the existing Immich
HTTPS album links in their browsers. They do not need Tailscale, a new SSID, a
hosts-file entry, or an Immich account when the owner uses an album share link.

## Live discovery, 2026-11-26

A request explicitly bound to the laptop's Wi-Fi interface reached the existing
Home Assistant proxy with HTTP 200. The upstream-facing Proxmox address is
reachable from Google Wi-Fi; the homelab's ingress address is not directly routed.
Immich returned 200 through Traefik. Google Wi-Fi currently uses automatic DNS,
which returns the homelab ingress address for Immich.

Exact addresses, hostnames, host identity, and interface names are in
`immich-wifi/network.sops.yaml`, encrypted with the repository's existing SOPS age
recipient. Do not copy them into the public blog or issue. Diagnostic scripts
load this encrypted inventory locally. Immich belongs to Flux
`photo-enrichment-preview`, tracking `codex/photo-enrichment-217`, not `master`.

## Managed configuration

`gitops/clusters/homelab/apps/photo-enrichment/immich-wifi/` contains the host
bundle, a generated ConfigMap, and its deployment Job. It is included by the
existing photo-enrichment Kustomization. The Job also mounts the SOPS-encrypted
network settings. It uses the existing SOPS-managed
`monitoring/nut-deploy-ssh-key` Secret. Its public SSH host key was verified over
the existing trusted management connection; strict host-key checking is enabled.

The Job installs Debian's HAProxy and dnsmasq-base packages on PVE, validates their
configurations, and manages three dedicated systemd units. HAProxy relays TLS
from the encrypted `RELAY_ADDRESS` on port 443 to the encrypted `TRAEFIK_HOSTNAME`
on port 443. Traefik continues
terminating TLS with its existing wildcard certificate. DNS listens on PVE's
ISP-facing address, on UDP and TCP port 53. Only Immich receives the local
override; other queries are forwarded to independent upstream resolvers.

Firewall rules allow the Google Wi-Fi WAN address and PVE's own checks. They
affect only the new listeners and never flush the host's firewall. HAProxy also
checks the client source and TLS SNI. Immich's distinct Traefik TLSOption makes a
mismatched HTTP Host return 421, preventing an accepted Immich TLS connection
from being used to reach another application's route. The existing Immich
private middleware remains in place; the proxy connects from PVE's homelab IP.

The public bundle uses variable placeholders. The Job transfers the decrypted
settings to a root-readable file on the host and renders the two daemon templates.
Run `bash scripts/immich-wifi/refresh-network-revision.sh` after changing the
encrypted settings: their ciphertext hash is included in the generated ConfigMap
so a settings change reruns the deployment too.

Kustomize hashes the ConfigMap content. A hash change updates the Job pod
template, and its Flux force annotation recreates the immutable Job. A completed
Job remains available for audit; no TTL causes it to rerun unexpectedly. This is
deployment-time convergence, not a periodic host drift controller. To deliberately
rerun the installer through GitOps, change a comment in its bundled host script.

## Deployment and verification

1. Run `bash scripts/immich-wifi/validate.sh --server`.
2. Review and commit the explicit files, after the repository's secret checks.
3. Fast-forward the existing Flux-tracked photo-enrichment branch, preserving
   concurrent work. Flux polls every minute; no manual Kubernetes apply is used.
4. Run `bash scripts/immich-wifi/watch-deployment.sh` until the Job completes.
5. Run `bash scripts/immich-wifi/check-access.sh` from a Mac on Google Wi-Fi.
   This binds requests to Wi-Fi so a wired homelab interface cannot hide errors.

The access checker first verifies UDP/TCP DNS, public-name resolution, valid TLS,
the Immich ping endpoint, rejected unrelated SNI, and rejected mismatched HTTP
Host. Exit 3 means those checks passed but Google Wi-Fi has not yet adopted the
custom resolver. Devices with explicit secure/private DNS may bypass local DNS;
use network-provided DNS for this private hostname.

## Google Home handoff

Only do this after the relay and resolver tests pass. In Google Home, open
Wi-Fi → Network settings → Advanced networking → DNS → Custom. Set the primary
IPv4 resolver to the decrypted `RELAY_ADDRESS`; leave the secondary empty if
accepted. Do not
use a public resolver as a secondary: clients could receive the old homelab IP.
Do not configure a public IPv6 resolver that bypasses the same override.

The router has a read-only local status endpoint; its DNS setting is changed
through the owner's Google Home session. Re-run the access checker afterwards.
Confirm a real shared album in both a phone browser and a laptop browser, with
Tailscale off. A 200 response for an application shell alone does not prove that
the album's API calls and thumbnails loaded.

Because Google Wi-Fi's WAN lease supplies the encrypted `GOOGLE_WAN_ADDRESS`, reserve that
existing lease on the upstream router when practical. If it changes, this setup
fails closed: update `GOOGLE_WAN_ADDRESS` in the SOPS-encrypted settings, refresh the
network revision, and commit through Git. The installer refuses an unexpected WAN address.

## Backups and rollback

PVE retains the initial firewall rules, routes, and installed-package inventory
under `/var/lib/immich-wifi/initial-backup/`, plus each replaced feature bundle
and dedicated unit files under `/var/lib/immich-wifi/backups/`. A failed activation
stops the new listeners and restores the prior feature files when present.

First restore Google Home DNS to **Automatic**, so normal internet DNS does not
depend on the resolver being removed. Then change the last argument in the
bundled `deploy.sh` remote invocation from `apply` to `rollback` and commit/push.
Flux reruns the Job, which disables its dedicated units and removes only its own
firewall rules. It leaves the installed binaries and audit backups on PVE and
does not touch the HA proxy, routing, certificate, or other Traefik applications.
Finally remove `immich-wifi` from the parent Kustomization and revert the dedicated
TLSOption if desired. Simply deleting a completed Kubernetes Job does not undo
its external host side effects.

## Validation record

On 2026-11-26, Flux applied commit `70e1f89`. The host Job completed in 18 seconds.
The image's POSIX shell, SSH client, and tar were verified before deployment.
Shell syntax, the complete Kustomize build, Git whitespace checks, and the
Kubernetes server-side dry run (after SOPS decryption) passed.

The host installed HAProxy `2.6.12-1+deb12u4` and dnsmasq-base `2.90-4~deb12u2`.
Both daemon configurations validated and all three dedicated units became active.
From Google Wi-Fi, direct UDP/TCP DNS returned the relay address, ordinary public
DNS resolved, and certificate-verified HTTPS returned Immich's `pong`. Unrelated
SNI was rejected; an accepted Immich TLS name with an unrelated HTTP Host returned
421. IPv6 queries did not leak an upstream address. A request deliberately bound
to the laptop's lab Ethernet interface was rejected by the new relay's source
rules. Google Wi-Fi's own resolver still used automatic DNS at this checkpoint;
the owner-facing Google Home DNS handoff and real album browser check are pending.
