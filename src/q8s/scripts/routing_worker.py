"""
Author: Vincent Hasse
License: MIT

Creates routing rules for Q8S host
"""
import subprocess
import socket

def get_ip():
    """
    Get the local machine's IP address by attempting to connect to an external IP.
    Even though the IP does not need to be reachable, this method helps determine the 
    outgoing network interface and IP address of the host.
    
    Returns:
        str: The detected IP address of the local machine, or '127.0.0.1' (localhost) if detection fails.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't have to be reachable
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

HOST_IP = get_ip()
VM_IP = "192.11." + HOST_IP.split(".")[3] + "." + HOST_IP.split(".")[3]
INTERFACE_NAME = "ens3"

commands = [f"sudo iptables -I FORWARD 1 -o virbr0 -d 192.11.{HOST_IP.split('.')[3]}.0/24 -m state --state NEW,RELATED,ESTABLISHED -j ACCEPT"]
#forward host port 2222 to vm ssh port 22
commands.append(f"sudo iptables -t nat -A PREROUTING -p tcp -i {INTERFACE_NAME} -d {HOST_IP} --dport 2222 -j DNAT --to-destination {VM_IP}:22")
#reroute everything but ports 22 and 2222 to VM
commands.append(f"sudo iptables -t nat -A PREROUTING -p tcp -m multiport ! --dports 22,2222 -i {INTERFACE_NAME} -d {HOST_IP} -j DNAT --to-destination {VM_IP}")
commands.append(f"sudo iptables -t nat -A PREROUTING -p udp -m multiport ! --dports 22,2222 -i {INTERFACE_NAME} -d {HOST_IP} -j DNAT --to-destination {VM_IP}")

#SNAT source of outgoing packets
commands.append(f"sudo iptables -t nat -I POSTROUTING 1 -s {VM_IP} -j SNAT --to-source {HOST_IP}")

#execute commands and save them in file for tracability
f= open("host_routing_commands.txt", "w")
for c in commands:
    f.write(c+"\n")
    subprocess.run(c.split())
f.close()
print("Changes applied to iptables!")