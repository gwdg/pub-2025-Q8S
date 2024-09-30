#!/bin/bash
mkdir -p /home/cloud/resources
cat > /home/cloud/resources/recreate_routing_rules_on_restart.sh << 'EOF'
#!/bin/bash
IPS=$(cat /home/cloud/resources/worker_ips.txt)
python3 /home/cloud/Q8S/src/q8s/scripts/routing_master.py "$IPS"
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