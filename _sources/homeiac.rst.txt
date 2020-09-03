Home Infrastructure As code (homeiac)
-------------------------------------

Documentation on setting up home servers using IaC.

Goal
****

Have home automation and other services available in a secure fashion while having the ability to manage them all via code.

Hardware
********

- 1 Raspberry PI - for running monitoring/pi-hole services using https://balena.io/
- 1 Raspberry PI 4 - for running backup / media server using ZFS
- 1 Raspberry PI - for running k3s and other development builds
- One Windows PC for running heavy duty stuff

Setup
*****

Setup Balena Managed Raspberry PI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Get the Balena image and follow instructions till the git clone part from https://www.balena.io/docs/learn/getting-started/raspberrypi3/nodejs/
- Add the homeiac application
- Conceptually application is a fleet of devices that you want a set of applications to be deployed
- Current understanding is that you cannot pick and choose what applications you want on a device. It is all or nothing
- Add your github ssh key so that it can talk to github repos
- Add https://github.com/marketplace/actions/balena-push to your github workflow after setting the BALENA_API_TOKEN (at the org level) and the BALENA_APPLICATION_NAME at the repo level (https://github.com/homeiac/home/settings/secrets)
- This is the link to the workflow - https://github.com/homeiac/home/blob/master/.github/workflows/balena_cloud_push.yml
- With this support, the goal of IaC for raspberry pi devices is achieved. There is no need for keeping OS and other services up to date. Everything is managed by Balena. All changes (unless you override using local mode) goes through github. The central docker-compose.yml controls what gets deployed. Each push to master automatically updates the devices.
- To disable wifi at runtime - Run the following from the cloud shell https://dashboard.balena-cloud.com/devices/

  ``nmcli radio wifi off``

  *  (To be verified) - Move the resin-wifi-config to resin-wifi-config.ignore as follows
     ``cd /mnt/boot/system-connections && mv resin-wifi-01 resin-wifi-01.ignore``

Setup media / backup Raspberry PI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Setup using Ubuntu 64 bit image from https://ubuntu.com/download/raspberry-pi
- create user ``pi``
- Upgrade OS and install zfs-dkms
   * Move /var and /home using the instructions from https://www.cyberciti.biz/faq/freebsd-linux-unix-zfs-automatic-mount-points-command/


.. code-block:: bash

  zpool create data /dev/sdb
  zfs create data/var
  cd /var
  cp -ax * /data/var
  cd .. && mv var var.old
  zfs set mountpoint=/var data/var
  zfs create data/home
  cd /home
  cp -ax * /data/home
  cd .. && mv home home.old
  zfs set mountpoint=/home data/home
  reboot
  rm -rf /home.old
  rm -rf /var.old

- Install node exporter using instructions from https://linuxhit.com/prometheus-node-exporter-on-raspberry-pi-how-to-install/#3-node-exporter-setup-on-raspberry-pi-running-raspbian
   * Download node exporter
   * Unpack and install it under /usr/local/bin
   * Install the systemd service

.. code-block:: bash

  cd ~
  wget https://github.com/prometheus/node_exporter/releases/download/v1.0.0/node_exporter-1.0.0.linux-armv7.tar.gz
  tar -xvzf node_exporter-1.0.0.linux-armv7.tar.gz
  sudo cp node_exporter-1.0.0.linux-armv7/node_exporter /usr/local/bin
  sudo chmod +x /usr/local/bin/node_exporter
  sudo useradd -m -s /bin/bash node_exporter
  sudo mkdir /var/lib/node_exporter
  sudo chown -R node_exporter:node_exporter /var/lib/node_exporter
  cd /etc/systemd/system/
  sudo wget https://gist.githubusercontent.com/gshiva/9c476796c8da54afe9fb231e984f49a0/raw/b05e28a6ca1c89e815747e8f7e186a634518f9c1/node_exporter.service
  sudo systemctl daemon-reload
  sudo systemctl enable node_exporter.service
  sudo systemctl start node_exporter.service
  systemctl status node_exporter.service
  cd ~

Setup iscsi server
~~~~~~~~~~~~~~~~~~

The following steps is required to create the iscsi targets for k3s.

.. code-block:: bash

  # install the targetcli to setup the iscsi targets
  # From https://linuxlasse.net/linux/howtos/ISCSI_and_ZFS_ZVOL
  sudo apt-get install targetcli-fb open-iscsi

  # create the sparse volumes for each netboot RPI for k3s /var/lib/rancher mount
  # k3s does not work over NFS
  sudo zfs create -s -V 50g data/4ce07a49data
  sudo zfs create -s -V 50g data/7b1d489edata
  sudo zfs create -s -V 50g data/e44d4260data

  # use target cli to create the targets
  sudo targetcli

  # *** VERY IMPORTANT ***
  # in order to restore the config after reboot enable the following service
  # and run it once
  sudo systemctl enable rtslib-fb-targetctl
  sudo systemctl start rtslib-fb-targetctl


Setup k3s (Kubernetes)
~~~~~~~~~~~~~~~~~~~~~~

Enable cgroup support by adding 'cgroup_memory=1 cgroup_enable=memory' in /boot/cmdline.txt

.. code-block:: bash

  cgroup_memory=1 cgroup_enable=memory

.. code-block:: bash

  cat /boot/cmdline.txt
  dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=PARTUUID=6f18a865-02 rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait cgroup_memory=1 cgroup_enable=memory

.. code-block:: bash

 curl -sfL https://get.k3s.io | sh -

The instructions are from https://opensource.com/article/20/3/kubernetes-raspberry-pi-k3s

Setup helm
~~~~~~~~~~

From https://helm.sh/docs/intro/install/

.. code-block:: bash

  curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3
  chmod 700 get_helm.sh
  ./get_helm.sh

  # add the repos
  helm repo add stable https://kubernetes-charts.storage.googleapis.com/
  helm repo add bitnami https://charts.bitnami.com/bitnami

Setup cloudflare for dynamic DNS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After setting up account in cloudflare, get the api token from https://dash.cloudflare.com/profile/api-tokens

Use k8s yaml cloudflare-ddns-deployment.yaml to run https://hub.docker.com/r/oznu/cloudflare-ddns/ image

Setup minion for k3s
~~~~~~~~~~~~~~~~~~~~

Follow instructions in https://www.raspberrypi.org/documentation/hardware/raspberrypi/bootmodes/net_tutorial.md

.. code-block:: bash

  sudo mkdir -p /nfs/client1
  sudo apt install rsync
  sudo rsync -xa --progress --exclude /nfs / /nfs/client1

After many attempts and a all-nighter, was not able to make Raspberry Model B Rev 2 to work (either as a tftp client _or_ a k3s node (it was not able to start any pods) ).

Setup LetsEncrypt + Traefik
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Traefik is already setup with k3s - so no additional work is required for that per se

Following instructions on https://opensource.com/article/20/3/ssl-letsencrypt-k3s for setting up LetsEncrypt

.. code-block:: bash

  kubectl create namespace cert-manager
  curl -sL \
 https://github.com/jetstack/cert-manager/releases/download/v0.11.0/cert-manager.yaml |\
 sed -r 's/(image:.*):(v.*)$/\1-arm:\2/g' > cert-manager-arm.yaml
  # change example.com to home.minibloks.com... don't know whether this really made a difference
  # changing this showed the padlock icon in chrome
  sed -r 's/example.com/home.minibloks.com/g' cert-manager-arm.yaml > cert-manager-arm.yaml
  kubectl apply -f cert-manager-arm.yaml

Modify the letsencrypt-issuer-staging.yaml with the following Contents
Required only if you want to testing... For prod you can skip the below

.. code-block:: yaml

 apiVersion: cert-manager.io/v1alpha2
 kind: ClusterIssuer
 metadata:
   name: letsencrypt-staging
 spec:
   acme:
    # The ACME server URL
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    # Email address used for ACME registration
    email: g_skumar@yahoo.com
    # Name of a secret used to store the ACME account private key
    privateKeySecretRef:
      name: letsencrypt-staging
    # Enable the HTTP-01 challenge provider
    solvers:
    - http01:
        ingress:
          class: traefik

Run the command

.. code-block:: bash

 sudo kubectl apply -f letsencrypt-issuer-staging.yaml

Create the certificate yaml le-test-certificate.yaml

.. code-block:: yaml

 apiVersion: cert-manager.io/v1alpha2
 kind: Certificate
 metadata:
  name: home-minibloks-net
  namespace: default
 spec:
  secretName: home-minibloks-net-tls
  issuerRef:
    name: letsencrypt-staging
    kind: ClusterIssuer
  commonName: home.minibloks.com
  dnsNames:
   - home.minibloks.com

Run the command

.. code-block:: bash

  sudo kubectl apply -f le-test-certificate.yaml


Create the letsencrypt-issuer-prod.yaml

.. code-block:: yaml

    apiVersion: cert-manager.io/v1alpha2
    kind: ClusterIssuer
    metadata:
    name: letsencrypt-prod
    spec:
    acme:
        # The ACME server URL
        server: https://acme-v02.api.letsencrypt.org/directory
        # Email address used for ACME registration
        email: g_skumar@yahoo.com
        # Name of a secret used to store the ACME account private key
        privateKeySecretRef:
        name: letsencrypt-prod
        # Enable the HTTP-01 challenge provider
        solvers:
        - http01:
            ingress:
            class: traefik

Apply it

.. code-block:: yaml

 sudo kubectl apply -f letsencrypt-issuer-prod.yaml

Create the sample site (optional):

.. code-block:: html

 <html>
 <head><title>K3S!</title>
   <style>
     html {
       font-size: 62.5%;
     }
     body {
       font-family: sans-serif;
       background-color: midnightblue;
       color: white;
       display: flex;
       flex-direction: column;
       justify-content: center;
       height: 100vh;
     }
     div {
       text-align: center;
       font-size: 8rem;
       text-shadow: 3px 3px 4px dimgrey;
     }
   </style>
 </head>
 <body>
   <div>Hello from K3S!</div>
 </body>
 </html>

Create a configMap out of it.

.. code-block:: bash

 sudo kubectl create configmap mysite-html --from-file index.html

Deploy the site using the following yaml, which has the required traefik tls ingress changes

.. code-block:: yaml

 apiVersion: apps/v1
 kind: Deployment
 metadata:
   name: mysite-nginx
   labels:
     app: mysite-nginx
 spec:
   replicas: 1
   selector:
     matchLabels:
       app: mysite-nginx
   template:
     metadata:
       labels:
         app: mysite-nginx
     spec:
       containers:
       - name: nginx
         image: nginx
         ports:
         - containerPort: 80
         volumeMounts:
         - name: html-volume
           mountPath: /usr/share/nginx/html
       volumes:
       - name: html-volume
         configMap:
           name: mysite-html
 ---
 apiVersion: v1
 kind: Service
 metadata:
   name: mysite-nginx-service
 spec:
   selector:
     app: mysite-nginx
   ports:
     - protocol: TCP
       port: 80
 ---
 apiVersion: networking.k8s.io/v1beta1
 kind: Ingress
 metadata:
   name: mysite-nginx-ingress
   annotations:
     kubernetes.io/ingress.class: "traefik"
     cert-manager.io/cluster-issuer: letsencrypt-prod
 spec:
   rules:
   - host: home.minibloks.com
     http:
       paths:
       - path: /
         backend:
           serviceName: mysite-nginx-service
           servicePort: 80
   tls:
   - hosts:
     - home.minibloks.com
     secretName: home-minibloks-com-tls


Structure
~~~~~~~~~

.. code-block:: bash

   <host-name>/
        /etc/
            rc.local
        /home/
            ip_display.py
        /<folder>/
            files


Open https://home.minibloks.com/ and profit!

Additional Hints
~~~~~~~~~~~~~~~~

Ability to run github actions locally totally rocks!!!

See https://github.com/nektos/act

``brew install nektos/tap/act``

then go to your folder and
``act -s ACCESS_TOKEN=<access_token_secret>``

For cross compiling install the following

.. code-block:: bash

  sudo apt-get install gcc-arm-linux-gnueabi build-essential flex bison


To get vcgencmd on ubuntu, follow the instructions in https://wiki.ubuntu.com/ARM/RaspberryPi

and add

``sudo add-apt-repository ppa:ubuntu-raspi2/ppa && sudo apt-get update``

the command will fail. After that update

``/etc/apt/sources.d/...focal.list``

change the release name to ``bionic``


To resolve the

``ping: k3smaster1.local: Temporary failure in name resolution``

problem.

Install the following:

.. code-block:: bash

   apt install -y samba libnss-winbind
   # modify /etc/nsswitch.conf line to add wins after the hosts line

   hosts:          files dns wins
   networks:       files


Developing packer image for raspberry pi
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ZFS compiling takes time and would be great if we had an image that ZFS was built in. Trying the instructions from https://github.com/solo-io/packer-builder-arm-image.

``sudo apt install kpartx qemu-user-static``


Content of scratch pad
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash


 # in some distributions the following might help with network issues
 update-alternatives --set iptables /usr/sbin/iptables-legacy
 update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
 update-alternatives --set arptables /usr/sbin/arptables-legacy
 update-alternatives --set ebtables /usr/sbin/ebtables-legacy

 export SERVER_IP=192.168.0.43
 export IP=192.168.0.43
 export USER=pi
 export NEXT_SERVER_IP=192.168.0.46
 export NEXT_MASTER_SERVER_IP=192.168.0.17

 curl -ssL https://get.k3sup.dev | sudo sh
 curl -sLS https://dl.get-arkade.dev | sh
 sudo install arkade /usr/local/bin/

 k3sup install \
  --ip $SERVER_IP \
  --user $USER \
  --cluster

 export KUBECONFIG=`pwd`/kubeconfig
 kubectl get node

 k3sup join \
  --ip $NEXT_SERVER_IP \
  --user $USER \
  --server-user $USER \
  --server-ip $SERVER_IP \
  --server

 export KUBECONFIG=`pwd`/kubeconfig
 kubectl get node

 adduser pi
 echo 'pi ALL=(ALL) NOPASSWD:ALL' >> visudo
 pi@k3smaster1:~$ cp /vagrant/rp_id* .
 pi@k3smaster1:~$ mkdir .ssh
 pi@k3smaster1:~$ mv rp_id* .ssh/
 pi@k3smaster1:~$ cd .ssh/
 pi@k3smaster1:~/.ssh$ ls -lth
 pi@k3smaster1:~/.ssh$ chmod 600 *
 pi@k3smaster1:~/.ssh$ mv rp_id_rsa.pub id_rsa.pub
 pi@k3smaster1:~/.ssh$ mv rp_idrsa id_rsa
 pi@k3smaster1:~/.ssh$ cat id_rsa.pub >authorized_keys


 # copy the keys and to authorized_keys in all the hosts

 # run this on the *real* master
 k3sup join \
  --ip $NEXT_MASTER_SERVER_IP \
  --user $USER \
  --server-user $USER \
  --server-ip $SERVER_IP \
  --server

 kubectl get node

 docker run \
  -e API_KEY="xxxx" \
  -e ZONE=minibloks.com \
  -e SUBDOMAIN=home \
  oznu/cloudflare-ddns

To get k3s working on k3smain
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

regular ZFS cannot be used for k3s as it relies on ext4, and you get these errors

``kube-system   0s          Warning   FailedCreatePodSandBox    pod/helm-install-traefik-9v4w7                 (combined from similar events): Failed to create pod sandbox: rpc error: code = Unknown desc = failed to create containerd task: failed to mount rootfs component &{overlay overlay [workdir=/var/lib/rancher/k3s/agent/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/69/work upperdir=/var/lib/rancher/k3s/agent/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/69/fs lowerdir=/var/lib/rancher/k3s/agent/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/1/fs]}: invalid argument: unknown``

so a ZVOL for /var/lib/rancher needs to be created

follow instructions in https://pthree.org/2012/12/21/zfs-administration-part-xiv-zvols/

.. code-block:: bash

  zfs create -V 30g data/rancher
  zfs list
  ls -l /dev/zvol/data/
  mkfs.ext4 /dev/zd64
  blkid
  vi /etc/fstab
  mkdir /var/lib/rancher
  mount -a



ZFS backup
~~~~~~~~~~

Using https://github.com/oetiker/znapzend for scheduled backups to pimaster

Followed the https://github.com/Gregy/znapzend-debian instructions for the debian package. Remember the package is present in the parent directory.

Installed it using

``dpkg -i z*.deb``

It kept saying pi@pimaster.local:/data/backup was not present even though it was there.
After hints from https://serverfault.com/questions/772805/host-key-verification-failed-on-znapzendzetup-create-command

Got it working.

See also https://github.com/oetiker/znapzend#running-by-an-unprivileged-user

Let the user ``pi`` in ``pimaster.local`` to have enough zfs permissions

Also did ``su && passwd && vi /etc/ssh/sshd_config && echo "Allowed Root Login GASP!" && echo "added to authorized keys (0-oo)"``

Reverted all of them once the ``pi`` user was working after the everything was made working using the ``root`` user.

Setting up router network for 2.4 Ghz devices
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The PC has a third adapter and an attempt was made to route it through Windows shared internet connection and also through the k3smaster VM. Probably due to some firewall issues, it didn't work.

Adding the adapter to the pimaster and running dnsmasq there worked.

Adding plugins to grafana
~~~~~~~~~~~~~~~~~~~~~~~~~

For installing a grafana plugin, ideally it should be added to the values.yaml during helm deployment. If missed, then the simplest way is to exec into the grafana container and use grafana cli to install the plugin from https://github.com/helm/charts/issues/9564

Specifically https://github.com/helm/charts/issues/9564#issuecomment-523666632

For anyone still wondering how to add new plugins without helm upgrade. If you are using persistent volumes you can access the grafana server pod to run grafana-cli plugins install <plugin-id>.

``kubectl exec -it grafana-pod-id -n grafana -- grafana-cli plugins install <plugin-id>``

Finally, delete the pod to restart the server:

``kubectl delete pod grafana-pod-id -n grafana``

For status map plugin the following actually works without requiring a Grunt build

``git clone git@github.com:flant/grafana-statusmap.git /var/lib/grafana/plugins/flant-statusmap-panel``

Fixing netplan dropping static IP when the link is disconnected problem
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Whenever the 2.4G private wireless network goes down or the cable is unplugged, netplan removes the static ip which is good. It doesn't bring it back up when the Access Point is back up again or when the network cable is plugged back in. It is a "known" problem and https://askubuntu.com/questions/1046420/why-is-netplan-networkd-not-bringing-up-a-static-ethernet-interface/1048041#1048041 had the solution

Remove the eth1 stanza from the netplan config and add something like this systemd config in /etc/systemd/network/10-eth1.network

.. code-block:: bash

  [Match]
  Name=eth1

  [Link]
  RequiredForOnline=no

  [Network]
  ConfigureWithoutCarrier=true
  Address=192.168.3.1/24
  Gateway=192.168.0.1
  DNS=192.168.0.17
  DNS=8.8.8.8
  DNS=1.1.1.1