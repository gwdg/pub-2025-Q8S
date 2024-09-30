#!bin/bash
# Author Vincent Hasse
# Licence: MIT
# initializes Kubernetes cluster with Flannel CNI, saves join-commands for worker- and control-plane-nodes

# requires installed kubernetes
# see https://www.youtube.com/watch?v=k3iexxiYPI8&ab_channel=MohamadLawand

#cluster init, flannel has fixed CIDR:
IP=$(/sbin/ifconfig ens3 | awk -F ' *|:' '/inet /{print $3}')
sudo kubeadm init --kubernetes-version 1.28.0 --pod-network-cidr=10.244.0.0/16 --control-plane-endpoint=$IP

#configuration
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

#use flannel
kubectl apply -f https://github.com/flannel-io/flannel/releases/download/v0.25.6/kube-flannel.yml

#save join-command 
CERT_KEY=$(sudo kubeadm init phase upload-certs --upload-certs)
CERT_KEY=$(sed -e 's/^.*key://p' <<< $CERT_KEY)
CERT_KEY=$(sed -e 's/^.*Namespace//p' <<< $CERT_KEY)
cd ~
mkdir -p resources
cd resources
sudo kubeadm token create --print-join-command > join_command_master.txt
sudo sed -i '1s/^/sudo /' /home/cloud/resources/join_command_master.txt
echo '--control-plane --certificate-key'$CERT_KEY >> join_command_master.txt
#automatically removes \n
JMASTER=$(cat join_command_master.txt)
echo $JMASTER > join_command_master.txt

sudo kubeadm token create --print-join-command > join_command_worker.txt
sudo sed -i '1s/^/sudo /' /home/cloud/resources/join_command_worker.txt
