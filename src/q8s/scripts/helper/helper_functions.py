"""
Author: Vincent Hasse
Licence: MIT

Helper functions for Q8S.
"""
import logging
import os
from pathlib import Path
import socket
import time
import paramiko
from kubernetes import client, config
from q8s.scripts.helper import exceptions
from q8s.scripts.helper.cluster_def import ClusterDefinition


logger = logging.getLogger("logger")

def check_if_ip_is_reachable(ip: str, port: int = 80, retries: int=40) -> bool:
    """
    Checks if a given IP is reachable over a specified port, retrying a given number of times.

    Args:
        ip (str): The IP address to check.
        port (int): The port to check reachability on (default is 80).
        retries (int): The number of retry attempts (default is 40).

    Returns:
        bool: True if the IP is reachable, False otherwise.
    """
    reachable = False
    for i in range(retries):
        logger.debug(f"Waiting for reachability of host {ip}, {i}th retry.")
        if isReachable(ip, port):
            reachable = True
            break
        else:
            time.sleep(10)
    return reachable



def isReachable(ip, port) -> bool:
    """
    Checks if a given IP and port are reachable using a ping command.

    Args:
        ip (str): The IP address to ping.
        port (int): The port to check reachability on.

    Returns:
        bool: True if the server is reachable, False if not.
        
    Raises:
        Q8sFatalError: If the system cannot execute OS commands.
    """
    try:
        code = os.system(f"ping -c 1 -W 3 {ip} -p {port} >/dev/null 2>&1")
        if code == 0:
            logger.debug(f"Server with ip {ip} is reachable.")
            return True
        else: return False
    except Exception as e:
        print(f"Cannot execute python os.system commands. Aborting...")
        logger.error(f"Cannot execute python os.system commands. Aborting...")
        raise exceptions.Q8sFatalError(f"Cannot execute python os.system commands. Aborting...")
    


def get_ssh_client(ip: str, key_filepath: str=str(Path.home()) + ("/.ssh/q8s-cluster")) -> paramiko.SSHClient:
    """
    Establishes an SSH connection to a given IP address using a private key.

    Args:
        ip (str): The IP address to connect to via SSH.
        key_filepath (str): The path to the SSH private key file (default is ~/.ssh/q8s-cluster).

    Returns:
        paramiko.SSHClient: A connected SSH client if successful, None otherwise.
    
    Raises:
        Q8sFatalError: If the SSH connection fails after retries.
    """
    client = paramiko.SSHClient()
    # equivalent of StrictHostKeyChecking=no
    client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
    connected = False
    for i in range (20):
        try:
            client.connect(hostname=ip, username="cloud", key_filename=key_filepath)
            connected = True
            break
        except paramiko.ssh_exception.NoValidConnectionsError as e:
            logger.debug(f"Could not ssh to host {ip}. starting try number {i}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"SSH error: " + str(e))
            exceptions.Q8sFatalError(f"SSH error: " + str(e))
            time.sleep(10)
    
    #test, if console is ready and commands can be executed (needs some time even after ssh connection is established)
    exit_code = 1
    TESTCOMMAND = "echo 'SSH-connection testcommand'"
    retries = 0
    while exit_code != 0 and retries < 10:
        _, stdout, stderr = client.exec_command(TESTCOMMAND)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            logger.debug(f"SSH test-command to host {ip} exited with code != 0: stdout: {stdout.readlines()}, stderr: {stderr.readlines()}")
            time.sleep(10)
            retries += 1

    if connected == True and exit_code == 0:
        return client
    else: return None



def send_file_via_sftp(ips: list[str], filepath: str, destination_path: str, key_filepath: str=str(Path.home()) + ("/.ssh/q8s-cluster")):
    """
    Sends a file to multiple IP addresses via SFTP.

    Args:
        ips (list[str]): A list of IP addresses to send the file to.
        filepath (str): The local path to the file to be sent.
        destination_path (str): The remote destination path where the file should be placed.
        key_filepath (str): The path to the SSH private key file (default is ~/.ssh/q8s-cluster).
    
    Raises:
        Q8sFatalError: If SSH connection to any IP fails.
    """
    for ip in ips:
        ssh_client = get_ssh_client(ip, key_filepath)
        if ssh_client == None:
            raise exceptions.Q8sFatalError(f"Host {ip} cannot be reached via SSH to send join command.")
        
        sftp_client = paramiko.SFTPClient.from_transport(ssh_client.get_transport())

        try:
            sftp_client.chdir(destination_path.rsplit("/", maxsplit=1)[0])
        except IOError:
            sftp_client.mkdir(destination_path.rsplit("/", maxsplit=1)[0])
            
        sftp_client.put(filepath, destination_path)
        logger.debug(f"File {filepath} sent to instance {ip}.")
        sftp_client.close()
        ssh_client.close()