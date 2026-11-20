#!/bin/bash
# Runs inside VM 105's root through the GitOps maintenance Job. No VM SSH.
set -euo pipefail
phase=${1:?prepare or install}
version=580.178.04-0ubuntu0.24.04.1
module_version=580.178.04
state=/var/lib/homelab-gpu-driver/$module_version
umask 077
mkdir -p "$state/rollback"
exec 9>"$state/lock"
flock -n 9
[[ $(hostname) == k3s-vm-pumped-piglet-gpu ]]
. /etc/os-release
[[ $VERSION_ID == 24.04 ]]
export DEBIAN_FRONTEND=noninteractive
if [[ $phase == prepare ]]; then
  if [[ -f $state/prepared ]]; then echo "Preparation already saved"; exit 0; fi
  [[ -f /etc/apt/sources.list.d/ubuntu.sources ]]
  apt-get -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources -o Dir::Etc::sourceparts=- update
  apt-cache policy nvidia-driver-580
  apt-cache madison nvidia-driver-580 | grep -F "$version" >/dev/null || { echo "Pinned target no longer on mirror; refresh Git desired version first"; exit 42; }
  apt-get -y install dpkg-repack
  dpkg-query -W -f='${Package} ${Version} ${db:Status-Status}\n' > "$state/packages-before.txt"
  apt-mark showmanual > "$state/manual-before.txt"
  cp -a /etc/apt/preferences.d "$state/preferences-before"
  cp -a /etc/default/grub "$state/grub-before"
  uname -r > "$state/kernel-before.txt"
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
  # Keep exact old driver binaries available even if the Ubuntu mirror changes.
  cd "$state/rollback"
  while read -r package installed status; do
    if [[ $status == installed && $installed == 535.288.01-0ubuntu0.24.04.1 ]]; then
      apt-get download "$package=$installed" || dpkg-repack "$package"
    fi
  done < "$state/packages-before.txt"
  apt-get -s install "nvidia-driver-580=$version" | tee "$state/apt-plan.txt"
  # Refuse unrelated removals. Review the saved plan before the install phase.
  if awk '/^Remv / && $2 !~ /nvidia/ {bad=1} END {exit !bad}' "$state/apt-plan.txt"; then
    echo 'Refusing unrelated package removals'; exit 1
  fi
  apt-get --download-only -y install "nvidia-driver-580=$version"
  touch "$state/prepared"
  echo 'PREPARED: rollback packages saved; target packages downloaded; no driver changed.'
elif [[ $phase == install ]]; then
  [[ -f $state/prepared ]]
  if [[ $(cat /sys/module/nvidia/version) == "$module_version" ]]; then
    echo 'Desired driver is already loaded'; exit 0
  fi
  apt-get -y --no-download install "nvidia-driver-580=$version"
  cat > /etc/apt/preferences.d/homelab-nvidia-driver <<EOF
Package: src:nvidia-graphics-drivers-580:any
Pin: version $version
Pin-Priority: 1001
EOF
  [[ $(modinfo -k "$(uname -r)" -F version nvidia) == "$module_version" ]]
  dkms status
  touch "$state/installed"
  if [[ ! -f $state/reboot-scheduled ]]; then
    systemd-run --unit=homelab-nvidia-580-reboot --on-active=30s /usr/bin/systemctl reboot
    touch "$state/reboot-scheduled"
  fi
  echo 'INSTALLED: VM reboot scheduled in 30 seconds to load the pinned driver.'
else
  echo 'Unknown phase'; exit 1
fi
