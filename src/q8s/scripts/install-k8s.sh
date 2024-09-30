#!bin/bash

#Author: Vincent Hasse
#Licence: MIT
#Installs containerd and Kubernetes v. 1.28

sudo apt update
#install containerd runtime
sudo apt install -y curl ca-certificates gnupg
sudo apt update
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y containerd.io

# containerd configuration
sudo containerd config default | sudo tee /etc/containerd/config.toml

# to avoid continous restart of etcd pod and hence error for kube-apiserver and other kube-system pods
# change SystemdCgroup to "true" in /etc/containerd/config.toml  
# see https://github.com/etcd-io/etcd/issues/13670
sudo sed -i 's|SystemdCgroup = false|SystemdCgroup = true|g' /etc/containerd/config.toml
sudo systemctl restart containerd

#change system variables
sudo modprobe overlay
sudo modprobe br_netfilter

sudo tee /proc/sys/net/bridge/bridge-nf-call-iptables <<EOF
1
EOF

sudo tee /proc/sys/net/ipv4/ip_forward <<EOF
1
EOF

sudo cat <<EOF | sudo tee /etc/modules-load.d/containerd
overlay
br_netfilter
EOF

cat <<EOF | sudo tee /etc/sysctl.d/99-kubernetes-cri.conf
net.bridge.bridge-nf-call-iptables=1
net.ip4.ip_forward=1
net.bridge.bridge-nf-call-ip6tables=1
EOF

#disable swapoff
sudo swapoff -a
#permanently
sudo sed -i '/ swap / s/^/#/' /etc/fstab

#install kubernetes components
sudo rm /etc/apt/sources.list.d/kubernetes.list
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
sudo apt update
sudo apt install -y kubelet=1.28.0-1.1 kubeadm=1.28.0-1.1 kubectl=1.28.0-1.1

#disable auto-update
sudo apt-mark hold kubectl kubeadm kubelet

sudo sysctl --system
