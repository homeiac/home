Welcome to homeiac's documentation!
===================================

Contents
---------

.. toctree::
   :maxdepth: 2

Home Infrastructure As code (homeiac)
-------------------------------------

Documentation on setting up home servers using IaC. 

Goal
****

Have home automation and other services available in a secure fashion while having the ability to manage them all via code.

Hardware
********

- 2 Raspberry PIs - one master and other minion for running management and routing tasks
- One Windows PC for running heavy duty stuff

Setup
*****

Setup master Raspberry PI
~~~~~~~~~~~~~~~~~~~~~~~~~

- Setup using Raspbian Buster Lite image from https://www.raspberrypi.org/downloads/raspbian/ 
- change the default password for user PI

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
---------

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
----------------

For cross compiling install the following

.. code-block:: bash

  sudo apt-get install gcc-arm-linux-gnueabi build-essential flex bison



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
----------------------------------------

ZFS compiling takes time and would be great if we had an image that ZFS was built in. Trying the instructions from https://github.com/solo-io/packer-builder-arm-image.

``sudo apt install kpartx qemu-user-static``


Content of scratch pad
----------------------

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
 pi ALL=(ALL) NOPASSWD:ALL
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





Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


