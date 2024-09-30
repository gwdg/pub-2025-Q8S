import subprocess
import sys
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

def create_master_routing(worker_ips):
    """
    Configures routing on the master node to direct traffic to worker nodes.

    Args:
        worker_ips (list): A list of IP addresses for the worker nodes.

    Raises:
        subprocess.CalledProcessError: If any of the iptables commands fail.
    """
    INTERFACE_NAME = "ens3"
    MASTER_IP = get_ip()
    commands = []
    commands.append(f"sudo iptables -I FORWARD 1 -o {INTERFACE_NAME} -m state --state NEW,RELATED,ESTABLISHED -j ACCEPT")
    for ip in worker_ips:
        ip_last = ip.split(".")[3]
        commands.append(f"sudo iptables -t nat -A OUTPUT -d 192.11.{ip_last}.{ip_last} -j DNAT --to-destination {ip}")
    
    #execute commands and save them for traceability
    f= open("master_routing_commands.txt", "w")
    for c in commands:
        f.write(c+"\n")
        subprocess.run(c.split())
    f.close()
    print("Changes applied to iptables!")


if __name__ == "__main__":
    ips = sys.argv[1].replace(" ", "").replace("[", "").replace("]", "").replace("'", "").split(",")
    create_master_routing(ips)