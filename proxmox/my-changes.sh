#!/bin/bash
apt-get install -y gnupg  lsb-release
DEBIAN_CODENAME=$(lsb_release -cs)
# Add Proxmox repository
echo "deb [arch=amd64] http://download.proxmox.com/debian/pve ${DEBIAN_CODENAME} pve-no-subscription" > /etc/apt/sources.list.d/pve-install-repo.list
wget https://enterprise.proxmox.com/debian/proxmox-release-bookworm.gpg -O /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg
# verify
sha512sum /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg
7da6fe34168adc6e479327ba517796d4702fa2f8b4f0a9833f5ea6e6b48f6507a6da403a274fe201595edc86a84463d50383d07f64bdde2e3658108db7d6dc87 /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg
# Update and install Proxmox VE
apt-get update && apt full-upgrade
apt install -y proxmox-default-kernel
apt-get install -y proxmox-ve postfix open-iscsi chrony zfsutils-linux zfs-initramfs
apt remove linux-image-amd64 'linux-image-6.1*'
echo "deb http://ftp.debian.org/debian bookworm main contrib non-free" >> /etc/apt/sources.list
apt update
apt install -y console-setup grub-pc
cat <<EOF > /etc/cloud/templates/hosts.debian.tmpl
## template:jinja
{#
This file (/etc/cloud/templates/hosts.debian.tmpl) is only utilized
if enabled in cloud-config.  Specifically, in order to enable it
you need to add the following to config:
   manage_etc_hosts: True
-#}
# Your system has configured 'manage_etc_hosts' as True.
# As a result, if you wish for changes to this file to persist
# then you will need to either
# a.) make changes to the master file in /etc/cloud/templates/hosts.debian.tmpl
# b.) change or remove the value of 'manage_etc_hosts' in
#     /etc/cloud/cloud.cfg or cloud-config from user-data
#
{# The value '{{hostname}}' will be replaced with the local-hostname -#}
{{public-ipv4}} {{fqdn}} {{hostname}}
# The following lines are desirable for IPv6 capable hosts
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF
update-grub
# Disable Proxmox Enterprise Repository
if [ -f /etc/apt/sources.list.d/pve-enterprise.list ]; then
    sed -i 's|^deb https://enterprise.proxmox.com/debian/pve|#&|' /etc/apt/sources.list.d/pve-enterprise.list
fi

# Add Proxmox No-Subscription Repository
echo "deb [arch=amd64] http://download.proxmox.com/debian/pve $(lsb_release -cs) pve-no-subscription" > /etc/apt/sources.list.d/pve-install-repo.list

# Verify Changes (for Packer Debugging)
grep -r "enterprise.proxmox.com" /etc/apt/sources.list* || echo "Proxmox Enterprise repo removed!"

