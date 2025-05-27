# K3s NVIDIA GPU Passthrough Guide — Proxmox VE + K3s

Stream GPU power into your K3s homelab: pass an NVIDIA GeForce RTX 3070 from
Proxmox into a K3s VM and accelerate AI, video, and compute workloads.

---

## Prerequisites

* **VT‑d** (Intel) or **AMD‑Vi** enabled **in BIOS › Advanced › System Agent**
* Proxmox node with an NVIDIA GPU installed (e.g. RTX 3070 on host `still‑fawn`)
* VM OS: Ubuntu 22.04 / 24.04 or Debian 12
* Existing K3s ≥ v1.32 cluster (API or GUI install)
* Host‑side tools: `lspci`, `dmesg`, `update-grub`, `modprobe`, `nvidia-ctk`,
  `kubectl`, `crictl`

> ⚠️ **Beware:** Most BIOSes ship with IOMMU/VT‑d disabled. Double‑check and
> turn it **on** before continuing.

---

## 1. Enable IOMMU & VFIO on Proxmox Host

```bash
# A) Add IOMMU flags to GRUB
sed -i 's/quiet/quiet intel_iommu=on iommu=pt/' /etc/default/grub
update-grub && reboot

# B) Load VFIO modules at boot
echo -e "vfio\nvfio_iommu_type1\nvfio_pci\nvfio_virqfd" | sudo tee /etc/modules
update-initramfs -u

# C) Blacklist host GPU drivers
echo -e "blacklist nouveau\nblacklist nvidia" | sudo tee /etc/modprobe.d/blacklist-gpu.conf
update-initramfs -u

# D) Bind GPU to VFIO — replace IDs with your lspci -nn output
echo 'options vfio-pci ids=10de:2484,10de:228b disable_vga=1' | sudo tee /etc/modprobe.d/vfio.conf
update-initramfs -u && reboot
```

### Verification

```bash
# Kernel enabled IOMMU?
dmesg | grep -E 'DMAR:.*IOMMU enabled'

# GPU bound to vfio-pci?
lspci -k -s 01:00.0 | grep 'vfio-pci'

# Every PCIe device isolated in its own IOMMU group?
for g in /sys/kernel/iommu_groups/*; do
  echo "IOMMU Group ${g##*/}:"
  for d in "$g"/devices/*; do
    echo -e "\t$(lspci -nns ${d##*/})"
  done
done
```

### IOMMU Setup Common Missteps

* Missing `iommu=pt` → inconsistent passthrough.
* Host driver not blacklisted → GPU never frees for VM.

---

## 2. Create & Configure the VM (Proxmox GUI)

1. **VM Options:** BIOS = **OVMF (UEFI)**, Machine = **q35**, CPU Type =
   **host**
2. **Hardware → Add → PCI Device:** choose `01:00.0 (GPU)` → enable
   **All Functions** and **PCI‑Express**
3. **Start VM**

### Verification (inside VM)

```bash
lspci -nn | grep -i nvidia
```

### VM Config Common Missteps

* Forgetting **All Functions** → passthrough of GPU *or* audio only.
* CPU model left at *Default* → AVX and other flags unavailable inside VM.
* CPU model should be Host

---

## 3. Install NVIDIA Drivers & Configure K3s Containerd

### Option A — Community Quick‑start

#### a. GPU Operator via Helm (fully automated)

```bash
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update
kubectl create namespace gpu-operator
helm install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator \
  --values values.yaml
```

#### b. Single shot `nvidia-ctk` injection (manual shim only)

```bash
sudo nvidia-ctk runtime configure \
  --runtime=containerd \
  --config /var/lib/rancher/k3s/agent/etc/containerd/config.toml
sudo systemctl restart k3s
```

> If you used **a. GPU Operator**, skip **b.** The Operator already performs the
> injection. The above is not verified. I did both and then it wasn't working
> before it started working.

### NVIDIA Install Verification

```bash
sudo crictl info | grep -A3 '"nvidia"'
nvidia-smi
```

**NVIDIA Common Missteps From Blogs**

* Editing `/etc/containerd/config.toml` (K3s ignores this file).
* Forgetting to run `nvidia-ctk` *before* K3s starts.

---

## 4. Deploy the NVIDIA Device Plugin

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.1/deployments/static/nvidia-device-plugin.yml
# (Optional) Restrict to GPU node only:
kubectl patch ds nvidia-device-plugin -n kube-system \
  --type=json -p '[{"op":"add","path":"/spec/template/spec/nodeSelector","value":{"nvidia.com/gpu.present":"true"}}]'
```

### K3s NVIDIA Integration Verification

```bash
kubectl get ds nvidia-device-plugin -n kube-system
kubectl logs -l app=nvidia-device-plugin -n kube-system | head -n 20
kubectl describe node still-fawn | grep -A2 Capacity  # Expect: nvidia.com/gpu: 1
```

---

## 5. Smoke‑test with a CUDA Pod

### gpu-test.yaml

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  restartPolicy: Never
  containers:
  - name: cuda-smi
    image: nvidia/cuda:11.0-base
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1
```

```bash
kubectl apply -f gpu-test.yaml
kubectl wait --for=condition=Succeeded pod/gpu-test --timeout=1m
kubectl logs gpu-test  # Expect full nvidia-smi output
```

---

## References

[NVIDIA GPU Operator](https://github.com/NVIDIA/gpu-operator)

[Proxmox GPU Passthrough Docs](https://pve.proxmox.com/wiki/Pci_passthrough)

[UntouchedWagons/K3S-NVidia: A guide on using NVidia GPUs for transcoding or AI in Kubernetes](https://github.com/UntouchedWagons/K3S-NVidia?tab=readme-ov-file#installing-the-gpu-operator)

[Installing the NVIDIA Container Toolkit — NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html#configuring-cri-o)

[NVIDIA/k8s-device-plugin: NVIDIA device plugin for Kubernetes](https://github.com/NVIDIA/k8s-device-plugin#quick-start)

[NVIDIA/k8s-device-plugin: NVIDIA device plugin for Kubernetes](https://github.com/NVIDIA/k8s-device-plugin#prerequisites)

[How to use GPUs with DevicePlugin in OpenShift 3.10](https://www.redhat.com/en/blog/how-to-use-gpus-with-deviceplugin-in-openshift-3-10)

[NVIDIA GPU passthrough with k3s? : r/kubernetes](https://www.reddit.com/r/kubernetes/comments/lopyu9/nvidia_gpu_passthrough_with_k3s/)

[QEMU / KVM CPU model configuration — QEMU documentation](https://qemu-project.gitlab.io/qemu/system/qemu-cpu-models.html)

[Fatal glibc error: CPU does not support x86-64-v2 · Issue #287 · JATOS/JATOS](https://github.com/JATOS/JATOS/issues/287)

[Installing the NVIDIA Container Toolkit — NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

[NVIDIA/k8s-device-plugin: NVIDIA device plugin for Kubernetes](https://github.com/NVIDIA/k8s-device-plugin#enabling-gpu-support-in-kubernetes)

[Adding A GPU node to a K3S Cluster – Radical Geek Technology Solution](https://radicalgeek.co.uk/pi-cluster/adding-a-gpu-node-to-a-k3s-cluster/)

[UntouchedWagons/K3S-NVidia: A guide on using NVidia GPUs for transcoding or AI in Kubernetes](https://github.com/UntouchedWagons/K3S-NVidia)

[Enable IOMMU or VT-d in your motherboard BIOS - BIOS - Tutorials - InformatiWeb](https://us.informatiweb.net/tutorials/it/bios/enable-iommu-or-vt-d-in-your-bios.html)

[still-fawn.maas details | maas MAAS](http://192.168.4.53:5240/MAAS/r/machine/sfem4w/summary)

[Intel® Core™ i5-4460 Processor](https://www.intel.com/content/www/us/en/products/sku/80817/intel-core-i54460-processor-6m-cache-up-to-3-40-ghz/specifications.html)

[edenreich/ollama-kubernetes: A POC I'm going to demo about how to deploy Ollama onto Kubernetes](https://github.com/edenreich/ollama-kubernetes)

[Enabled GPU passthrough of Intel HD 610 with GVT-g in Proxmox 8 | Proxmox Support Forum](https://forum.proxmox.com/threads/enabled-gpu-passthrough-of-intel-hd-610-with-gvt-g-in-proxmox-8.134461/)

[Homelab K3s HA Setup](https://chatgpt.com/c/6824e84b-78b8-8007-a843-7d03241b2c32)

[Enabled GPU passthrough of Intel HD 610 with GVT-g in Proxmox 8 | Proxmox Support Forum](https://forum.proxmox.com/threads/enabled-gpu-passthrough-of-intel-hd-610-with-gvt-g-in-proxmox-8.134461/)
