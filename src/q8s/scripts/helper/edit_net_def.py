"""
Author: Vincent Hasse
Licence: MIT

Edits the .xml description file of a libvirt network, adding:
- Cloudflare DNS
- set MTU to 1450
- changes IP range to 192.11.x.x, where x is the last digit of the primary IP address of the primary interface of the executing machine

imput: filepath to net-def.xml file
output:
'newNetDef.xml' containing the changes saved at the net-def.xml's path
"""
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

filepath = sys.argv[1]

netDef = open(str(filepath)+"/net-def.xml", "r")
newNetDef = open(str(filepath)+"/newDefault.xml", "w")

lines = netDef.readlines()
formatting = ""
last_digit = get_ip().split(".")[3]
for line in lines:
    if "</ip>" in line:
        formatting = line.split('<')[0]
        newNetDef.write(line)
        newNetDef.write(formatting + "<dns>\n")
        newNetDef.write(formatting + "  <forwarder addr='1.1.1.1'/>\n")
        newNetDef.write(formatting + "</dns>\n")
    elif "<ip address=" in line:
        formatting = line.split('<')[0]
        #set MTU
        newNetDef.write(formatting + f"<mtu size='1450'/>\n")
        #define subnet 
        newNetDef.write(formatting + f"<ip address='192.11.{last_digit}.1' netmask='255.255.255.0'>\n")
    elif "<range start=" in line:
        formatting = line.split('<')[0]
        newNetDef.write(formatting + f"<range start='192.11.{last_digit}.2' end='192.11.{last_digit}.254'/>\n")
    else:
         newNetDef.write(line)
netDef.close()
newNetDef.close()
