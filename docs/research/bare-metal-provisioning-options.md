# Bare Metal Provisioning Options Research

**Date**: 2025-02-11
**Context**: Evaluating GitOps-compatible bare metal provisioning for homelab (consumer HW) and work (Dell R640/R960 with iDRAC)

---

## TL;DR

| Environment | Hardware | Best Option |
|-------------|----------|-------------|
| Homelab | Consumer boards (no BMC) | **MAAS** (already deployed) |
| Work | Dell R640/R960 (iDRAC/Redfish) | **Metal3** or **Ansible + iDRAC** |
| Windows bare metal | Any | **FOG Project** or **Ansible + iDRAC** |

---

## Tool Comparison Matrix

| Tool | Linux BM | Windows BM | Requires BMC | K8s Native | Complexity |
|------|----------|------------|--------------|------------|------------|
| **MAAS** | ✅ | ⚠️ Fragile | ❌ Optional | ❌ REST API | Medium |
| **Metal3** | ✅ | ❌ | ✅ Required | ✅ CRDs | High |
| **Foreman** | ✅ | ✅ | ❌ Optional | ❌ | High |
| **WDS/MDT** | ❌ | ✅ | ❌ | ❌ | Medium |
| **FOG Project** | ✅ | ✅ | ❌ | ❌ | Medium |
| **Ansible + iDRAC** | ✅ | ✅ | ✅ Required | ❌ | Low |

---

## MAAS (Metal as a Service)

**What it is**: Canonical's bare metal provisioning system. PXE boots machines, deploys OS images.

**Current state**: Already deployed in homelab (evidenced by `.maas` hostnames in inventory).

### Strengths
- Works without BMC (manual power, Wake-on-LAN)
- Mature, production-ready (Canonical backed)
- REST API for automation
- Supports custom images via Packer

### Weaknesses
- Not Kubernetes-native (REST API, not CRDs)
- Windows support is fragile (see below)

### Windows on MAAS - The Reality

**Historical context**: Windows images previously required **MAAS Image Builder (MIB)**, which was paywalled behind Ubuntu Advantage subscription.

**Current state**: Canonical now provides free [packer-maas](https://github.com/canonical/packer-maas) templates for Windows.

**Does it work?** Fragile. GitHub issues show:
- [#278](https://github.com/canonical/packer-maas/issues/278): Image builds but won't deploy ("tar: not a tar archive")
- [#302](https://github.com/canonical/packer-maas/issues/302): "invalid magic number" on UEFI boot
- [#335](https://github.com/canonical/packer-maas/issues/335): sysprep fails on Server 2022

Users who got it working had to patch templates manually. Not turnkey.

### GitOps Integration

MAAS has REST API but no K8s CRDs. Options to GitOps-ify:
1. **Terraform MAAS Provider** - Declare machines in HCL
2. **Crossplane** - K8s CRDs that call MAAS API
3. **Custom Operator** - Build K8s operator for MAAS

---

## Metal3.io

**What it is**: Kubernetes-native bare metal provisioning. Uses Ironic (OpenStack) under the hood.

### How It Works

```yaml
apiVersion: metal3.io/v1alpha1
kind: BareMetalHost
metadata:
  name: server-01
spec:
  bmc:
    address: idrac-virtualmedia://192.168.1.10/redfish/v1/Systems/System.Embedded.1
    credentialsName: server-01-bmc-credentials
  bootMACAddress: "aa:bb:cc:dd:ee:ff"
  online: true
```

Apply with `kubectl`, machine provisions. True GitOps.

### Requirements

- **BMC Required**: IPMI, Redfish, iDRAC, iLO
- **Bootstrap K8s cluster**: Need existing cluster to run Metal3 controllers
- **Linux only**: No Windows support (Ironic limitation)

### Homelab Verdict

❌ **Not viable** - Consumer hardware lacks BMC.

### Work (R640/R960) Verdict

✅ **Viable** - iDRAC provides Redfish API.

---

## WDS (Windows Deployment Services)

**What it is**: Microsoft's native PXE-based Windows deployment.

### Requirements

| Requirement | Notes |
|-------------|-------|
| Windows Server | Any version, can be VM |
| **Active Directory** | **Hard requirement** |
| DHCP | PXE options 66/67 |
| DNS | AD-integrated |

### Verdict

❌ **Not viable without AD** - Standing up domain infrastructure just for provisioning is overkill.

---

## FOG Project

**What it is**: Open-source imaging solution. "WDS without AD."

**Website**: https://fogproject.org/

### How It Works

1. Install FOG server (Linux - can be LXC on Proxmox)
2. PXE boot target machine
3. Capture image from golden machine OR deploy existing image
4. Web UI for management

### Strengths
- No AD required
- Works for Windows and Linux
- Web UI
- Free, open source

### Weaknesses
- Image-based (not declarative provisioning)
- No GitOps integration out of box
- Requires manual image capture/maintenance

### Use Case

Good for occasional Windows bare metal deployments where MAAS Windows support is too fragile.

---

## Ansible + iDRAC (For Dell Servers)

**What it is**: Direct automation via Dell iDRAC Redfish API. No provisioning infrastructure needed.

### How It Works

```bash
# Mount ISO via iDRAC virtual media
racadm -r <idrac-ip> -u root -p <pass> \
  remoteimage -c -l "http://fileserver/windows.iso"

# Set one-time boot to virtual CD
racadm set BIOS.OneTimeBoot.OneTimeBootMode OneTimeBootSeq
racadm set BIOS.OneTimeBoot.OneTimeBootSeqDev Optical.iDRACVirtual.1-1

# Power cycle
racadm serveraction powercycle
```

Post-install, Ansible connects via WinRM for configuration.

### Ansible Modules

- `dellemc.openmanage` collection
- `community.general.redfish_*` modules

### Example Playbook Structure

```yaml
- name: Provision Windows on Dell server
  hosts: idrac_hosts
  tasks:
    - name: Mount Windows ISO
      dellemc.openmanage.idrac_virtual_media:
        idrac_ip: "{{ idrac_ip }}"
        idrac_user: "{{ idrac_user }}"
        idrac_password: "{{ idrac_password }}"
        virtual_media:
          - insert: true
            image: "http://fileserver/win2022.iso"

    - name: Set boot to virtual CD
      dellemc.openmanage.idrac_bios:
        idrac_ip: "{{ idrac_ip }}"
        # ... boot configuration

    - name: Power cycle
      dellemc.openmanage.idrac_power:
        idrac_ip: "{{ idrac_ip }}"
        reset_type: "ForceRestart"

- name: Post-install configuration
  hosts: windows_servers
  tasks:
    - name: Wait for WinRM
      wait_for_connection:
        timeout: 1800

    - name: Configure Windows
      # ... ansible.windows modules
```

### GitOps Pattern

```
Git repo (playbooks + inventory)
    ↓
CI/CD or manual trigger
    ↓
Ansible → iDRAC API → Server provisions
    ↓
Ansible → WinRM → Post-config
```

### Strengths
- No infrastructure footprint (runs from laptop)
- Works for "hidden" servers
- Full Windows support
- GitOps-compatible (playbooks in Git)
- Dell-native API, well-supported

### Weaknesses
- Dell-specific (iLO needs different modules for HP)
- Not declarative like Metal3
- Requires manual ISO hosting

---

## Recommendations

### Homelab (Consumer Hardware, No BMC)

**Keep using MAAS** for Linux bare metal. It's already deployed and working.

For Windows bare metal (if ever needed):
1. Try MAAS + packer-maas first
2. Fall back to FOG Project if MAAS is too fragile
3. Or just: USB install + Ansible post-config (pragmatic for <5 machines/year)

### Work (Dell R640/R960 with iDRAC)

**Two paths depending on goals:**

#### Path A: Minimal Footprint ("Hidden" Servers)
Use **Ansible + iDRAC**:
- No visible infrastructure
- Playbooks live in Git
- Run from laptop
- Full Windows + Linux support

#### Path B: Full GitOps
Use **Metal3** for Linux, **Ansible + iDRAC** for Windows:
- Metal3 gives true K8s-native provisioning
- Still need Ansible for Windows (Metal3 doesn't support it)
- Requires bootstrap K8s cluster for Metal3 controllers

---

## References

### MAAS
- [MAAS Documentation](https://maas.io/docs)
- [packer-maas GitHub](https://github.com/canonical/packer-maas)
- [packer-maas Windows templates](https://github.com/canonical/packer-maas/tree/main/windows)

### Metal3
- [Metal3.io](https://metal3.io/)
- [Metal3 Documentation](https://book.metal3.io/)
- [Cluster API Provider Metal3](https://github.com/metal3-io/cluster-api-provider-metal3)

### FOG Project
- [FOG Project](https://fogproject.org/)
- [FOG Documentation](https://docs.fogproject.org/)

### Dell iDRAC Automation
- [Dell OpenManage Ansible Modules](https://github.com/dell/dellemc-openmanage-ansible-modules)
- [Redfish Ansible Collection](https://galaxy.ansible.com/community/general)
- [racadm CLI Reference](https://www.dell.com/support/manuals/en-us/idrac9-lifecycle-controller-v6.x-series/idrac9_6.xx_racadm_pub/introduction)

### Windows Deployment (Traditional)
- [WDS Documentation](https://docs.microsoft.com/en-us/windows/deployment/windows-deployment-scenarios-and-tools)
- [MDT Documentation](https://docs.microsoft.com/en-us/mem/configmgr/mdt/)

---

## Tags

bare-metal, baremetal, provisioning, maas, metal3, ironic, wds, fog, idrac, redfish, ipmi, windows-server, gitops, ansible, pxe, dell, r640, r960
