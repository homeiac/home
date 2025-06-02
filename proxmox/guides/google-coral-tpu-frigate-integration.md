# Google Coral TPU and Frigate Integration Guide

This guide walks you through setting up a Coral USB Accelerator with a Proxmox
host running a Frigate container. It explains the prerequisites, device
initialization, udev configurations, and integration steps to enhance object
detection performance using the Coral TPU.

## 1. Prerequisites

1. **Coral USB Accelerator**

   * Have your Coral USB Accelerator (e.g., Coral USB Accelerator v2) ready.

2. **Proxmox Host Details**

   * A Proxmox node (v7.x or newer) where you can create and modify LXCs.
   * A working Frigate LXC/container already running Frigate with your camera
     feeds set up.

3. **Tools to Install on the Proxmox Host**

   ```bash
   apt update
   apt install -y usbutils udev python3 python3-venv git unzip
   ```

   * `usbutils`: for running `lsusb`

   * `udev`: to create custom rules for the Coral device

   * `python3`/`python3-venv`: to run PyCoral examples before LXC passthrough

   * `git`/`unzip`: to clone and extract repositories

   > **Link:** LX(C) container config paths:
   > [https://forum.proxmox.com/threads/where-are-lx-c-container-configurations-stored.59780/](https://forum.proxmox.com/threads/where-are-lx-c-container-configurations-stored.59780/)

---

## 2. Plug in the Coral and Verify on the Host

1. **Insert the Coral USB** into a USB 3.0 port on your Proxmox host (avoid
   using a passive USB hub).

2. **Check `lsusb` Immediately**

   ```bash
   lsusb | grep -i coral
   ```

   * If it shows something like:

     ```bash
     Bus 003 Device 006: ID 1a6e:089a Global Unichip Corp.
     ```

     that means the Coral is still in “Global Unichip” mode (`1a6e:089a`) and
     hasn’t been initialized yet.

3. **Install the Edge TPU Runtime on the Host**

   ```bash
   wget https://dl.google.com/coral/edgetpu_api/edgetpu_runtime_20210620.zip
   unzip edgetpu_runtime_20210620.zip
   # Choose whichever matches your hardware:
   dpkg -i libedgetpu1-max_*.deb    # or libedgetpu1-std_<version>.deb
   dpkg -i libedgetpu-dev_<version>.deb  # (optional, for headers)
   ```

   * **Why?** This installs the kernel driver so that once you run a PyCoral
     example, the device will re-enumerate as `18d1:9302 Google Inc.` instead of
     `1a6e:089a`.
   * **Link:** Coral USB “Get Started” (Linux):
     [https://coral.ai/docs/accelerator/get-started/#pycoral-on-linux](https://coral.ai/docs/accelerator/get-started/#pycoral-on-linux)

4. **Install Pyenv on the Host** (to get Python 3.9)

   ```bash
   # Follow the Real Python tutorial:
   curl https://pyenv.run | bash
   # Then add these lines to ~/.bashrc (or ~/.zshrc):
   export PATH="$HOME/.pyenv/bin:$PATH"
   eval "$(pyenv init --path)"
   eval "$(pyenv init -)"
   eval "$(pyenv virtualenv-init -)"
   source ~/.bashrc

   # Install Python 3.9 via pyenv:
   pyenv install 3.9.16
   pyenv virtualenv 3.9.16 coral-tpu
   pyenv activate coral-tpu
   ```

   * **Why?** PyCoral’s Python package isn’t compatible with Python 3.10+, so
     you need a 3.9 environment.
   * **Link:** Managing Python versions with Pyenv:
     [https://realpython.com/intro-to-pyenv/](https://realpython.com/intro-to-pyenv/)

5. **Clone the PyCoral and Test Data Repos**

   ```bash
   git clone https://github.com/google-coral/pycoral.git
   git clone https://github.com/google-coral/test_data.git
   ```

   * **Why?** `pycoral` contains example scripts like `classify_image.py`;
     `test_data` provides models and images those examples use.

6. **Install PyCoral via pip**

   ```bash
   pip install numpy
   pip install pycoral
   ```

   * **Why?** The Ubuntu package `python3-pycoral` can be outdated or missing.
     Installing via `pip` ensures you have the latest library.
   * **Link:** (User note) “I couldn’t `apt install pycoral`, so I did `pip
     install pycoral`.”

---

## 3. Wake Up the Coral Device (Host)

1. **Run the Classification Example** From the directory *one level above* both
   `pycoral/` and `test_data/`:

   ```bash
   cd ~/           # or wherever you cloned both repos
   python3 pycoral/examples/classify_image.py \
     --model test_data/mobilenet_v2_1.0_224_inat_bird_quant_edgetpu.tflite \
     --labels test_data/inat_bird_labels.txt \
     --input test_data/parrot.jpg
   ```

   * **What Happens:**

     * PyCoral loads the quantized MobileNet V2 Bird model onto the Coral and
       runs inference on `parrot.jpg`.
     * In the process, the Coral’s USB interface switches from `1a6e:089a`
       (Global Unichip) to `18d1:9302` (Google Inc.).

2. **Verify the Mode Switch**

   ```bash
   lsusb | grep -E "18d1:9302"
   ```

   You should see something like:

   ```bash
   Bus 003 Device 005: ID 18d1:9302 Google Inc.
   ```

   * If it still shows `1a6e:089a`, double-check you installed the correct
     `libedgetpu1-*` package.

3. **Record the Bus/Device Path**

   * In this example, it’s `/dev/bus/usb/003/005`. You’ll use that path in the
     LXC config.

---

## 4. Create Udev Rules (Host)

1. **Create a New Rule File**

   ```bash
   cat <<EOF > /etc/udev/rules.d/98-coral.rules
   SUBSYSTEMS=="usb", ATTRS{idVendor}=="1a6e", ATTRS{idProduct}=="089a", OWNER="root", MODE="0666", GROUP="plugdev"
   SUBSYSTEMS=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", OWNER="root", MODE="0666", GROUP="plugdev"
   EOF
   ```

   * **Why?** This ensures that when the Coral switches modes, it always gets
     `0666` permissions so any process (including the LXC) can open it.

2. **Reload and Trigger the Rules**

   ```bash
   udevadm control --reload-rules && udevadm trigger
   ```

   * **Confirm Permissions**

     ```bash
     ls -l /dev/bus/usb/003/005
     ```

     You should see:

     ```bash
     crw-rw-rw- 1 root plugdev 189, 4 Jun  1 16:15 /dev/bus/usb/003/005
     ```

   > **Link:** Proxmox forum: USB passthrough to LXC
   > [https://forum.proxmox.com/threads/passthrough-usb-device-to-lxc-keeping-the-path-dev-bus-usb-00x-00y.127774/](https://forum.proxmox.com/threads/passthrough-usb-device-to-lxc-keeping-the-path-dev-bus-usb-00x-00y.127774/)

---

## 5. Passthrough Coral into Your Frigate LXC

1. **Locate the LXC Config File** On the Proxmox host:

   ```bash
   /etc/pve/lxc/<CTID>.conf
   ```

   Replace `<CTID>` with your container ID (e.g., `113`).

2. **Edit `/etc/pve/lxc/113.conf`** and append:

   ```ini
   # Allow USB character devices
   lxc.cgroup2.devices.allow: c 189:* rwm

   # Bind-mount the Coral device into the container
   dev0: /dev/bus/usb/003/005
   ```

   * **Explanation:**

     * `c 189:* rwm` grants the LXC permission to access all USB character
       devices (major 189).
     * `dev0: /dev/bus/usb/003/005` ensures the Coral shows up inside the
       container at the same path.

3. **Restart the LXC**

   ```bash
   pct stop 113
   pct start 113
   ```

   * **Verify Inside the LXC**

     ```bash
     pct exec 113 -- lsusb | grep -i "Google Inc"
     ```

     You should see:

     ```bash
     Bus 003 Device 005: ID 18d1:9302 Google Inc.
     ```

   > If it still appears as `Global Unichip` inside the container, run the
   > classification example on the host again (so it’s already in `18d1:9302`
   > mode) and then restart the LXC.

---

## 6. (Optional) Install PyCoral & Edge TPU Runtime Inside the LXC

If you’d like to run PyCoral scripts from within your Frigate LXC (or Frigate
itself needs Python bindings), do this inside the container:

1. **Enter the LXC**

   ```bash
   pct exec 113 -- bash
   ```

2. **Install the Edge TPU Runtime**

   ```bash
   wget https://dl.google.com/coral/edgetpu_api/edgetpu_runtime_20210620.zip
   unzip edgetpu_runtime_20210620.zip
   dpkg -i libedgetpu1-max_*.deb  # or libedgetpu1-std_<version>.deb
   ```

   * **Why?** The container needs the same kernel driver to open
     `/dev/bus/usb/003/005`.

3. **Install PyCoral via pip**

   ```bash
   apt update
   apt install -y python3-pip python3-venv
   python3 -m venv /opt/py39
   source /opt/py39/bin/activate
   pip install numpy
   pip install pycoral
   ```

   * **Why?** You can’t rely on `apt install python3-pycoral`. Installing via
     `pip` ensures compatibility.

4. **Test Inside the Container**

   ```bash
   python3 - <<EOF
   from pycoral.utils.edgetpu import list_edge_tpus
   print(list_edge_tpus())
   EOF
   ```

   * Expected output:

     ```bash
     ['/dev/apex_0']   # or ['/dev/bus/usb/003/005'], depending on your setup
     ```

---

## 7. Update Frigate’s Configuration to Use the Coral

1. **Edit Frigate’s `config.yml`** (e.g., `/etc/frigate/config.yml` inside the
   LXC):

   * **Before (CPU/OpenVINO):**

     ```yaml
     detectors:
       ov:
         type: openvino
         device: CPU
         model:
           path: /openvino-model/FP16/ssdlite_mobilenet_v2.xml
     model:
       width: 300
       height: 300
       input_tensor: nhwc
       input_pixel_format: bgr
       labelmap_path: /openvino-model/coco_91cl_bkgr.txt
     ```

   * **After (Edge TPU):**

     ```yaml
     detectors:
       coral:
         type: edgetpu
         device: usb
     ```

   * **Why?** This switches Frigate’s object detector from CPU/OpenVINO to the
     Coral TPU. You can remove or ignore the previous `model:` block because
     Coral will load its built-in COCO model by default (or you can supply your
     own `.tflite` and `.txt` if desired).

2. **Restart Frigate** inside the LXC:

   ```bash
   pct exec 113 -- supervisorctl restart frigate
   ```

   * Verify the logs show something like:

     ```bash
     [frigate.detectors.utils] Starting EdgeTPU detector on usb:0
     ```

---

## 8. Verify Performance Gains

1. **Check Frigate Logs**

   * Look for “EdgeTPU” messages rather than “OpenVINO.”
   * Typical log line on startup:

     ```bash
     Detected Edge TPU at /dev/bus/usb/003/005
     ```

2. **Monitor CPU Usage**

   * In the Proxmox UI or by running `htop` inside the LXC, confirm that CPU
     usage for object detection has dropped significantly.
   * **Expected improvements:**

     * On a USB 2.0 port, inference might be ~ 40 ms/frame.
     * On a USB 3.0 port, inference should be < 10 ms/frame.
   * Overall, you’ll often see a 50–70 % CPU reduction compared to CPU/OpenVINO.

---

## 9. Troubleshooting Checklist

* **Coral Still Shows “Global Unichip Corp.” Inside LXC**

  1. Make sure you ran the PyCoral `classify_image.py` example on the **host**
     before starting the container.
  2. Verify that `udevadm control --reload-rules && udevadm trigger` was
     executed after creating `/etc/udev/rules.d/98-coral.rules`.
  3. Confirm that the host’s `lsusb` shows `ID 18d1:9302 Google Inc.` before you
     start the LXC.

* **Permission Denied When Accessing `/dev/bus/usb/003/005`**

  1. Check `ls -l /dev/bus/usb/003/005` on both host and inside LXC—permissions
     should be `crw-rw-rw- root plugdev`.
  2. Ensure Frigate runs as `root` (or a user in the `plugdev` group).

* **LXC Fails to Start with USB Errors**

  1. Double-check `/etc/pve/lxc/113.conf`—the `dev0:` path must exactly match
     the host’s `/dev/bus/usb/XXX/YYY`.
  2. Confirm `lxc.cgroup2.devices.allow: c 189:* rwm` appears above the `dev0:`
     line.
  3. If you plug the Coral into a different port (so the bus/device changes),
     update that path and restart the LXC.

* **Edge TPU Runtime Version Issues**

  * Some Coral hardware requires `libedgetpu1-std` instead of `-max`. If you see
    “Cannot open device” errors, uninstall any existing `libedgetpu1-*` packages
    and install the alternate variant.

* **Frigate Doesn’t Detect the Coral**

  1. Inside LXC, run `dmesg | grep -i edgetpu`—you should see the Edge TPU
     driver loading.
  2. Verify `lsusb` inside LXC shows `18d1:9302 Google Inc.`
  3. Check Frigate logs for any “Failed to open device” messages.

* **USB 2.0 vs. 3.0 Performance**

  * If you plug into a USB 2.0 port, inference times may hover around ~ 40 ms.
    On a USB 3.0 port, expect < 10 ms. Move the Coral to a USB 3.0 port for best
    performance.

---

## 10. Embedded Links & References

1. **Coral “Get Started” Docs**
   [https://coral.ai/docs/accelerator/get-started/#pycoral-on-linux](https://coral.ai/docs/accelerator/get-started/#pycoral-on-linux)

2. **Pyenv Installation Guide**
   [https://realpython.com/intro-to-pyenv/](https://realpython.com/intro-to-pyenv/)

3. **Proxmox USB Passthrough Discussion**
   [https://forum.proxmox.com/threads/passthrough-usb-device-to-lxc-keeping-the-path-dev-bus-usb-00x-00y.127774/](https://forum.proxmox.com/threads/passthrough-usb-device-to-lxc-keeping-the-path-dev-bus-usb-00x-00y.127774/)

4. **Coral Global Unichip Info (Reddit)**
   [https://www.reddit.com/r/Proxmox/comments/1cx7git/my_usb_coral_shows_as_global_unichip_corp_when/](https://www.reddit.com/r/Proxmox/comments/1cx7git/my_usb_coral_shows_as_global_unichip_corp_when/)

5. **Frigate Object Detectors (Edge TPU Section)**
   [https://docs.frigate.video/configuration/object_detectors/#single-usb-coral](https://docs.frigate.video/configuration/object_detectors/#single-usb-coral)

6. **Google Coral Test Data (models/images)**
   [https://github.com/google-coral/test_data/tree/104342d2d3480b3e66203073dac24f4e2dbb4c41](https://github.com/google-coral/test_data/tree/104342d2d3480b3e66203073dac24f4e2dbb4c41)

7. List of links that were super useful in debugging issues:

* [Frigate LCX and Coral TPU PCI :
  r/Proxmox](https://www.reddit.com/r/Proxmox/comments/1gtrt5r/frigate_lcx_and_coral_tpu_pci/)
* [Get started with the USB Accelerator |
  Coral](https://coral.ai/docs/accelerator/get-started/#pycoral-on-linux)
* [Managing Multiple Python Versions With pyenv – Real
  Python](https://realpython.com/intro-to-pyenv/)
* [Passthrough USB device to LXC keeping the path /dev/bus/usb/00x/00y | Proxmox
  Support
  Forum](https://forum.proxmox.com/threads/passthrough-usb-device-to-lxc-keeping-the-path-dev-bus-usb-00x-00y.127774/)
* [My USB Coral shows as Global Unichip Corp. when using the command lsusb. :
  r/Proxmox](https://www.reddit.com/r/Proxmox/comments/1cx7git/my_usb_coral_shows_as_global_unichip_corp_when/)
* [python - Pycoral: but it is not going to be installed - Stack
  Overflow](https://stackoverflow.com/questions/77897444/pycoral-but-it-is-not-going-to-be-installed)
* [python - A module that was compiled using NumPy 1.x cannot be run in NumPy
  2.0.0 - Stack
  Overflow](https://stackoverflow.com/questions/78641150/a-module-that-was-compiled-using-numpy-1-x-cannot-be-run-in-numpy-2-0-0)
* [google-coral/test_data at
  104342d2d3480b3e66203073dac24f4e2dbb4c41](https://github.com/google-coral/test_data/tree/104342d2d3480b3e66203073dac24f4e2dbb4c41)
* [Where are LX(C) container configurations stored? | Proxmox Support
Forum](https://forum.proxmox.com/threads/where-are-lx-c-container-configurations-stored.59780/)
* [\[SOLVED\] - Pass USB Device to LXC | Proxmox Support
Forum](https://forum.proxmox.com/threads/pass-usb-device-to-lxc.124205/)
* [Plex LXC GPU Passthrough :
  r/Proxmox](https://www.reddit.com/r/Proxmox/comments/1cneob0/plex_lxc_gpu_passthrough/)
* [Object Detectors |
  Frigate](https://docs.frigate.video/configuration/object_detectors/#single-usb-coral)
* [Coral - USB3 same speed as USB2 - Configuration - Home Assistant
  Community](https://community.home-assistant.io/t/coral-usb3-same-speed-as-usb2/687223/3)

---

## TODO

* **Verify that the `dev0: /dev/bus/usb/003/005` entry works consistently**—if
  you move the Coral to a different port, update this path accordingly and
  restart the LXC.
* Also whether `lxc.mount.entry: /dev/bus/usb/003/005 dev/bus/usb/003/005 none
  bind,optional,create=file` which was stopping from the container starting due
  to

```bash
safe_mount: 1425 No such file or directory - Failed to mount "/dev/serial/by-id" onto "/usr/lib/x86_64-linux-gnu/lxc/rootfs/dev/serial/by-id"
safe_mount: 1425 No such file or directory - Failed to mount "/dev/ttyUSB0" onto "/usr/lib/x86_64-linux-gnu/lxc/rootfs/dev/ttyUSB0"
safe_mount: 1425 No such file or directory - Failed to mount "/dev/ttyUSB1" onto "/usr/lib/x86_64-linux-gnu/lxc/rootfs/dev/ttyUSB1"
safe_mount: 1425 No such file or directory - Failed to mount "/dev/ttyACM0" onto "/usr/lib/x86_64-linux-gnu/lxc/rootfs/dev/ttyACM0"
safe_mount: 1425 No such file or directory - Failed to mount "/dev/ttyACM1" onto "/usr/lib/x86_64-linux-gnu/lxc/rootfs/dev/ttyACM1"
safe_mount: 1425 No such file or directory - Failed to mount "/dev/fb0" onto "/usr/lib/x86_64-linux-gnu/lxc/rootfs/dev/fb0"
run_buffer: 571 Script exited with status 17
lxc_setup: 3948 Failed to run autodev hooks
do_start: 1273 Failed to setup container "113"
sync_wait: 34 An error occurred in another process (expected sequence number 4)
TASK ERROR: startup for container '113' failed
```

can be added back instead of `dev0:` which seems to dedicate the TPU to the
container instead of sharing it.
