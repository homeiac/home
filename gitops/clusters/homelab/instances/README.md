# Crossplane-Managed Instances

This directory contains VM and LXC declarations for Crossplane to manage via Proxmox.

## How It Works

1. **Git** → Flux syncs YAML files to K8s cluster
2. **Crossplane** → Reconciles desired state with Proxmox
3. **Proxmox** → Creates/updates VMs and LXCs

## Creating New VMs

Copy `rancher-server.yaml` as a template:

```bash
cp rancher-server.yaml my-new-vm.yaml
# Edit VMID, name, specs
# Add to kustomization.yaml
# Commit and push
```

## Adopting Existing VMs/LXCs

Use the `external-name` annotation to adopt existing infrastructure:

```yaml
metadata:
  annotations:
    crossplane.io/external-name: "112"  # Existing VMID (example: docker LXC)
spec:
  deletionPolicy: Orphan  # Don't delete if CR removed from Git
```

Generate YAML from existing VM/LXC:

```bash
# Generate from existing LXC (example: docker LXC on fun-bedbug)
./scripts/crossplane/import-lxc.sh 112 > docker-host.yaml

# Generate from existing VM
./scripts/crossplane/import-vm.sh 200 > my-vm.yaml
```

## Safety Notes

- **New VMs**: Will be created by Crossplane
- **Adopted VMs**: Use `deletionPolicy: Orphan` to prevent accidental deletion
- **Test first**: Use non-essential VMs (like rancher-server) to validate before adopting production

## File Structure

| File | VMID | Node | Purpose |
|------|------|------|---------|
| rancher-server.yaml | 200 | pumped-piglet | RKE2 eval (test) |
| ~~frigate-nvr.yaml~~ | ~~113~~ | ~~fun-bedbug~~ | **Removed** — Frigate migrated to K3s pod (see `apps/frigate/`) |
