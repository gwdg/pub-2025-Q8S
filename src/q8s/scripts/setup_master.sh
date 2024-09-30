#!bin/bash
# Author: Vincent Hasse
# License: MIT
# installs kubernetes, creates routing rules and joins the Q8S cluster as a control-plane node

sudo sh -c 'echo "GNUTLS_CPUID_OVERRIDE=0x1" >> /etc/environment'
sudo apt update
#automatically select default in case of conflicts with configuration files
sudo apt upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

cd ~
#install kubernetes
echo "Installing Kubernetes..."
sudo bash /home/cloud/Q8S/src/q8s/scripts/install-k8s.sh > /home/cloud/kubeinit.log
#create routing rules
echo "creating routing rules..."
IPS=$(cat /home/cloud/resources/worker_ips.txt)
sudo sysctl -w net.ipv4.ip_forward=1 && sudo sed -i '/^net.ipv4.ip_forward/d' /etc/sysctl.conf && echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
python3 /home/cloud/Q8S/src/q8s/scripts/routing_master.py "$IPS"
#add the routing rules on restart
bash /home/cloud/Q8S/src/q8s/scripts/helper/make_master_routing_persistent.sh

#join cluster as control-plane node
echo " --v=5" >> /home/cloud/resources/join_command.txt
tr -d '\n' < join_command.txt > temp.txt && mv temp.txt join_command.txt
echo -e "\n Joining cluster as control-plane node...\n" 
echo -e "\n Joining cluster\n" >> /home/cloud/kubeinit.log
bash /home/cloud/resources/join_command.txt >> /home/cloud/kubeinit.log
mkdir -p /home/cloud/.kube