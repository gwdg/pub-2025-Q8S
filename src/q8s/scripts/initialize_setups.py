"""
Author: Vincent Hasse
License: MIT

Functions for initializing the setup of Q8S hosts and masters
"""
from pathlib import Path
import logging
import time
from q8s.scripts import helper
from q8s.scripts.helper import helper_functions
import q8s.scripts.helper.exceptions as exceptions


logger = logging.getLogger("logger")


def init_host_setup(giturl: str, ip: str):
    """
    Initializes a host setup on a remote server by executing a series of commands via SSH.

    Args:
        giturl (str): A URL that can be used to clone Q8S.
        ip (str): The IP address of the remote host to be set up.

    Returns:
        int: The exit code from the setup command execution. A return code of 0 indicates success.

    Raises:
        exceptions.Q8sFatalError: If the host is unreachable or if the SSH client cannot be established.
    """
    PATH_TO_HOST_SETUP_SCRIPT = "~/Q8S/src/q8s/scripts/setup_host.sh"
    # export  GNUTLS_CPUID_OVERRIDE=0x1 to make git clone work; see https://askubuntu.com/questions/1420966/method-https-has-died-unexpectedly-sub-process-https-received-signal-4-after
    COMMAND = f"echo 'wait for cloud-init'; cloud-init status --wait  > /dev/null 2>&1; export  GNUTLS_CPUID_OVERRIDE=0x1; cd ~; sudo apt update; sudo apt install -y git; echo 'cloning git repo'; git clone {giturl}; cd ~/Q8S; sudo apt install -y python3-pip; pip install .; bash {PATH_TO_HOST_SETUP_SCRIPT} > /home/cloud/setup.log"

    reachable = helper_functions.check_if_ip_is_reachable(ip)
    if not(reachable):
        print(f"Host with ip: {ip} not reachable for initialization. Aborting cluster creation.")
        logger.debug(f"Host with ip: {ip} not reachable for initialization. Aborting cluster creation.")
        raise exceptions.Q8sFatalError(f"Host with ip: {ip} not reachable for initialization. Aborting cluster creation.")
    logger.debug(f"Host {ip} reachable with ping. Starting setup via ssh")
    
    client = helper_functions.get_ssh_client(ip)
    
    if client == None:
        logger.debug(f"Host {ip} cannot be reached for setup via SSH.")
        raise exceptions.Q8sFatalError(f"Host {ip} cannot be reached for setup via SSH.")

    _, stdout, stderr = client.exec_command(COMMAND)
    code = stdout.channel.recv_exit_status()
    #mit print nicht parallel -> ohne? nicht getested, ansonsten das ganze in subprocesses verpacken
    #print(f"\nSTDERR:\n{stderr.readlines()}\n\nSTDOUT:\n{stdout.readlines()}")

    client.close()
    logger.debug(f"Server {ip} setup return code: {code}. Should be 0.")
    return code


def init_master_setup(giturl: str, ip: str) -> str:
    """
    Initializes the setup of a master node on a remote server by executing a series of commands via SSH.

    Args:
        giturl (str): A URL that can be used to clone Q8S.
        ip (str): The IP address of the master node to be set up.

    Returns:
        int: The exit code from the setup command execution. A return code of 0 indicates success.

    Raises:
        exceptions.Q8sFatalError: If the master node is unreachable or if the SSH client cannot be established.
    """
    PATH_TO_MASTER_SETUP_SCRIPT = "~/Q8S/src/q8s/scripts/setup_master.sh"
    COMMAND = f"echo 'wait for cloud-init'; cloud-init status --wait  > /dev/null 2>&1; export  GNUTLS_CPUID_OVERRIDE=0x1; cd ~; sudo apt update; sudo apt install -y git; echo 'cloning git repo'; git clone {giturl}; cd ~/Q8S; sudo apt install -y python3-pip; pip install .; bash {PATH_TO_MASTER_SETUP_SCRIPT} > /home/cloud/setup.log"

    reachable = helper_functions.check_if_ip_is_reachable(ip)
    if not(reachable):
        print(f"Master node with ip: {ip} not reachable for initialization. Aborting cluster creation.")
        logger.debug(f"Master node with ip: {ip} not reachable for initialization. Aborting cluster creation.")
        raise exceptions.Q8sFatalError(f"Master node with ip: {ip} not reachable for initialization. Aborting cluster creation.")
    logger.debug(f"Master node {ip} reachable with ping. Starting setup via ssh")

    client = helper_functions.get_ssh_client(ip)
    if client == None:
        raise exceptions.Q8sFatalError(f"Host {ip} cannot be reached for setup via SSH.")
    
    _, stdout, stderr = client.exec_command(COMMAND)
    code = stdout.channel.recv_exit_status()
    logger.debug(f"Server {ip} setup return code: {code}. Should be 0.")
    client.close()
    return code


