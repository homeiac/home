# An album link should not require a VPN lesson

Sharing family photos should mean sending a link. My Immich server already had
HTTPS and album sharing, but a phone on the ordinary home Wi-Fi could not reach
it unless its owner enabled Tailscale or joined the lab network. A laptop plugged
into the lab switch could open the same link, which made the problem easy to miss.

The fix starts by separating a name from a route. DNS knew the name of my Immich
server. It returned a private address on the lab subnet. That answer did not give
the Google Wi-Fi router a route to that subnet.

## Read the diagram, then verify it

My network documentation described three segments: Google Wi-Fi for everyday
devices, the upstream ISP network, and the homelab. A Proxmox host had interfaces
on all three. More usefully, an existing Home Assistant proxy already let a
Wi-Fi device reach a lab service through that host's upstream-facing interface.

I checked the current interfaces and explicitly bound a request to the laptop's
Wi-Fi interface. The existing Home Assistant proxy returned HTTP 200. That was
better evidence than a successful request from the laptop's default route: the
laptop also had an Ethernet connection into the lab. Some addresses in the old
diagram had changed, so copying the diagram directly would have been a mistake.

## Keep Traefik in charge of HTTPS

The resulting path reuses that reachable host, with a TCP relay for Immich:

```text
Phone or laptop on Google Wi-Fi
    → reachable local host:443
    → existing Traefik HTTPS listener
    → Immich
```

The relay passes encrypted TLS through. It does not have a copy of the wildcard
certificate and does not terminate HTTPS. Traefik still selects the Immich route
and presents the certificate already used by the rest of the lab. There is no
internet port forward and no new certificate request.

There is a subtle consequence to forwarding a shared ingress listener: a plain
TCP relay could also carry connections for the other applications behind it.
HAProxy therefore checks the source and permits only Immich's TLS server name.
That check alone is not the whole boundary. A client can send an Immich TLS name
and a different HTTP Host header. Immich receives a distinct Traefik TLSOption so
Traefik rejects that mismatch with HTTP 421. Both cases belong in the acceptance
checks, alongside a successful Immich request.

## Configure DNS once for the Wi-Fi

A small DNS-only resolver on the reachable host returns the relay address for
the existing Immich hostname. All other names go to ordinary upstream DNS.
Public wildcard DNS remains unchanged. Google Wi-Fi's custom DNS setting makes
this answer available to its clients without editing every phone or laptop.

The resolver must be tested before changing that setting: once selected, it also
handles ordinary internet DNS for the Wi-Fi. A public secondary resolver would
not provide the private override, so it is not an interchangeable backup. Devices
configured to bypass network DNS need to use the network resolver for this name.

This preserves the existing album URL. Immich's share-link feature lets visitors
view an album without creating accounts. Its term “public share link” describes
who can use the link; it does not make an unreachable private server reachable
or require opening the server to the internet.

## Use a Kubernetes Job to configure the external host

The Proxmox host is outside Kubernetes, but its desired configuration can still
live in Git. A ConfigMap carries the installer, service units, relay configuration,
and DNS configuration. A Kubernetes Job mounts that bundle and an existing
SOPS-managed SSH key, then runs the installer on the Proxmox host with strict
host-key checking.

Flux watches the configuration. Kustomize's ConfigMap content hash changes when
the bundle changes; the Job's force annotation lets Flux replace its immutable
pod template and execute the new installer. The installer checks that it is on
the expected host, checks the live network assumptions, saves backups, validates
both daemon configurations, and activates the dedicated services. A failed
activation restores the previous feature configuration.

The repository is public, so the network-specific settings and SSH host identity
are encrypted with SOPS. The public ConfigMap contains reusable templates; Flux
decrypts a separate settings Secret in the cluster. A hash of the encrypted file
also participates in the ConfigMap revision, so changing an address reruns the
installer without publishing the address in Git or in this post.

This pattern needs an honest rollback story. Deleting the Job does not remove
the services it installed elsewhere. The bundle has an explicit rollback action,
and the runbook restores Google Wi-Fi's normal DNS before removing the resolver.
The completed Job is also not a continuous host drift controller; another Git
change is needed to rerun it.

## Test the path the family will use

The repeatable acceptance check binds to Wi-Fi and verifies DNS over UDP and TCP,
normal internet-name resolution, valid HTTPS, Immich's API, rejected unrelated
TLS names, and rejected mismatched HTTP Hosts. It then asks Google Wi-Fi's own
resolver for the hostname to confirm the router has adopted the override.

Finally, open a real shared album on a phone and laptop with Tailscale off. A
successful ping endpoint is useful evidence, but it does not establish that an
album's API calls, thumbnails, or videos loaded. The goal is a working album link
on the devices people already use.

At the first deployment checkpoint, Flux applied the encrypted settings and the
host Job completed in 18 seconds. The Wi-Fi-bound DNS, HTTPS, and hostname rejection
checks passed. The remaining handoff was selecting the tested resolver in Google
Home, followed by opening a real album on the family's devices. That distinction
matters: a working server path and a completed router configuration are separate
results. After the owner saved the setting, queries to Google Wi-Fi's own resolver
returned the relay address over UDP and TCP, while ordinary internet names still
resolved. That completed the DNS handoff; the final human check is opening a real
album in a phone or laptop browser.

Implementation and current verification results are in the
[runbook](../../runbooks/immich-google-wifi.md). Vendor references:
[Immich sharing](https://docs.immich.app/features/sharing/),
[Google Wi-Fi custom DNS](https://support.google.com/googlehome/answer/6274141), and
[Traefik TLS options and hostname matching](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/crd/http/ingressroute/#tls-options).
