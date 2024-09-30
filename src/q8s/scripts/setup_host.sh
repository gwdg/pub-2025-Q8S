#!bin/bash
# Author: Vincent Hasse
# License: MIT
# sets up libvirt network, creates VM based on hostname and starts it, creates routing rules, installs required packages

#otherwise there might be problems with apt update 
sudo sh -c 'echo "GNUTLS_CPUID_OVERRIDE=0x1" >> /etc/environment'

sudo apt update
echo -e "Installing packages\n"
#automatically select default option in case of conflicts with configuration files 
sudo apt upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

sudo apt install -y net-tools dnsutils git cloud-image-utils

#QEMU
sudo apt install -y qemu-system-x86 qemu-system-aarch64 qemu-efi-aarch64 

#libvirt
echo -e "\nInstalling libvirt\n"
sudo apt install -y libvirt-daemon-system virtinst
sudo sed -i 's|#user = "root"|user = "root"|g' /etc/libvirt/qemu.conf 
sudo sed -i 's|#group = "root"|group = "root"|g' /etc/libvirt/qemu.conf 
sudo systemctl restart libvirtd
#sudo adduser $USER libvirt --> not necessary as cloud is member of 'sudo'-group

echo -e "\nSetting up network\n"
#destroy old default network
sudo virsh net-destroy default
#add dns to default network
# https://libvirt.org/formatnetwork.html
sudo cp /etc/libvirt/qemu/networks/default.xml /home/cloud/net-def.xml
sudo chmod 666 /home/cloud/net-def.xml
#undefine old network
sudo virsh net-undefine default
echo -e "\nChanging net-definition\n"
python3 /home/cloud/Q8S/src/q8s/scripts/helper/edit_net_def.py /home/cloud
#define and start new default network
sudo cp /home/cloud/newDefault.xml /etc/libvirt/qemu/networks/default.xml
sudo virsh net-define /etc/libvirt/qemu/networks/default.xml
sudo virsh net-autostart default
sudo virsh net-start default
#cleanup and save default-backup
sudo rm /home/cloud/newDefault.xml
sudo mv /home/cloud/net-def.xml /home/cloud/net-def.xml.bak

cd /home/cloud
mkdir -p /home/cloud/resources
sudo chown cloud resources/ 

echo -e "\nInstalling guest...\n"
python3 /home/cloud/Q8S/src/q8s/scripts/install_guest.py > /home/cloud/install_guest.log
#get mac address of vm
VIRSH_COMMAND="$(cat /home/cloud/resources/virsh-command.txt) --print-xml"
$VIRSH_COMMAND > /home/cloud/resources/vm_dump.xml
VM_MAC="$(cat /home/cloud/resources/vm_dump.xml | grep 'mac address' | awk -F'\"' '$0=$2')"
echo $VM_MAC > /home/cloud/resources/debug_mac.log
#assign static ip to vm where the last digits are equal to the host's last digits
DIGITS=$(hostname -I | cut -d' ' -f 1 | cut -d'.' -f 4)
sudo virsh net-update default add-last ip-dhcp-host "<host mac='$VM_MAC' name='vm-$HOSTNAME' ip='192.11.$DIGITS.$DIGITS'/>" --live --config

#setting VM behavior when shutdown, restarted and when crashing. Options can be found at https://libvirt.org/formatdomain.html
TEMP_XML="/home/cloud/resources/vm_dump.xml"

if grep -q "<on_poweroff>" "$TEMP_XML"; then
    sudo sed -i 's|<on_poweroff>.*</on_poweroff>|<on_poweroff>destroy</on_poweroff>|g' "$TEMP_XML"
else
    sudo sed -i '/<\/domain>/i <on_poweroff>destroy</on_poweroff>' "$TEMP_XML"
fi

if grep -q "<on_reboot>" "$TEMP_XML"; then
    sudo sed -i 's|<on_reboot>.*</on_reboot>|<on_reboot>restart</on_reboot>|g' "$TEMP_XML"
else
    sudo sed -i '/<\/domain>/i <on_reboot>restart</on_reboot>' "$TEMP_XML"
fi

if grep -q "<on_crash>" "$TEMP_XML"; then
    sudo sed -i 's|<on_crash>.*</on_crash>|<on_crash>restart</on_crash>|g' "$TEMP_XML"
else
    sudo sed -i '/<\/domain>/i <on_crash>restart</on_crash>' "$TEMP_XML"
fi

#create routing rules
echo -e "\nCreating routing rules..."
python3 /home/cloud/Q8S/src/q8s/scripts/routing_worker.py
sudo sysctl -w net.ipv4.ip_forward=1 && sudo sed -i '/^net.ipv4.ip_forward/d' /etc/sysctl.conf && echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
#add the routing rules on restart
cat > /home/cloud/resources/recreate_routing_rules_on_restart.sh << 'EOF'
#!/bin/bash
python3 /home/cloud/Q8S/src/q8s/scripts/routing_worker.py
EOF

sudo chmod +x /home/cloud/resources/recreate_routing_rules_on_restart.sh

sudo bash -c "cat > /etc/systemd/system/recreate_q8s_routing_rules.service << 'EOF'
[Unit]
Description=Recreate the iptables routing rules for the q8s-cluster

[Service]
ExecStart=/home/cloud/resources/recreate_routing_rules_on_restart.sh
Type=oneshot
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable recreate_q8s_routing_rules.service

#install vm
cd /home/cloud/resources
echo -e "\nStarting VM..."
sudo virsh define /home/cloud/resources/vm_dump.xml
sudo virsh start vm-$HOSTNAME

echo -e "\nHost setup finished, VM starting."