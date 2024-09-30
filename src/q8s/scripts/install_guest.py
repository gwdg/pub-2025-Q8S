"""
:author: Vincent Hasse
License: MIT
installs new QEMU VM in libvirt based on config file
"""

from itertools import takewhile
import os
from pathlib import Path
import subprocess
import socket
from q8s.scripts.helper import exceptions
from q8s.scripts.helper.cluster_def import VmType, load_cluster_data
import urllib.request

def write_virsh_command(path_to_cluster_data: str="/home/cloud/resources/cluster.yaml", path_to_keyfile: str="/home/cloud/resources/q8s-cluster.pub", path_to_join_command: str="/home/cloud/resources/join_command.txt"):
    """
    Downloads a cloud image, resizes it, creates necessary metadata, and generates a virsh command for VM setup.

    Args:
        path_to_cluster_data (str): The path to the cluster data YAML file. Default is "/home/cloud/resources/cluster.yaml".
        path_to_keyfile (str): The path to the SSH public key file. Default is "/home/cloud/resources/q8s-cluster.pub".
        path_to_join_command (str): The path to the join command file. Default is "/home/cloud/resources/join_command.txt".

    Returns:
        None: The function does not return a value, but it performs several file operations.

    Raises:
        exceptions.Q8sFatalError: If the architecture of the VM type is unsupported.
    """
    if not Path(path_to_cluster_data).is_file():
        print(f"Cannot find {path_to_cluster_data}!")
        return
    cluster_data = load_cluster_data(Path(path_to_cluster_data))
    hostname = socket.gethostname()
    vm_typename = hostname.split("-", maxsplit=2)[2]
    vm_type = cluster_data.vm_types.types[vm_typename]
    ssh_key = open(path_to_keyfile, "r").read()
    join_command = open(path_to_join_command, "r").read().rstrip()

    #download respective iso, resize, for arm create pflash images for boot
    url = ""
    if vm_type.architecture == "x86_64":
        url = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
    elif vm_type.architecture == "arm_64":
        url = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-arm64.img"
    else:         
        raise exceptions.Q8sFatalError(f"Unsupported architecture {vm_type.architecture}")
    print(f"Downloading image from {url}...")
    urllib.request.urlretrieve(url, "/home/cloud/resources/" + url.rsplit("/", maxsplit=1)[1])
    
    print(f"Resizing image...")
    if vm_type.architecture == "x86_64":
        subprocess.run(f"qemu-img resize /home/cloud/resources/jammy-server-cloudimg-amd64.img +{vm_type.storage}G", shell=True)
    elif vm_type.architecture == "arm_64":
        subprocess.run(f"qemu-img resize /home/cloud/resources/jammy-server-cloudimg-arm64.img +{vm_type.storage}G", shell=True)
        create_arm_efi_and_nvram("/home/cloud/resources")

    #create user and metadata
    create_cloudimg_seed("/home/cloud/resources", ssh_key, f"vm-{hostname}", join_command)
    print("seed.img created.")
    #create command
    command = create_virsh_command(f"vm-{hostname}",vm_type)
    with open("/home/cloud/resources/virsh-command.txt", "w", encoding='utf-8') as f:
        f.write(command)

def create_virsh_command(name: str, vm_type: VmType) -> str:
    """
    Generates a virsh command for creating a virtual machine with the specified configuration.

    Args:
        name (str): The name of the virtual machine.
        vm_type (VmType): An object containing the specifications of the virtual machine, 
                          including architecture, CPU model, number of CPUs, and RAM.

    Returns:
        str: The constructed virsh command for creating the VM.

    Raises:
        exceptions.Q8sFatalError: If the VM architecture is unsupported.

    Description:
        - This function constructs a command for the `virt-install` utility to create a 
          virtual machine using the provided parameters.
        - The command is tailored based on the architecture of the VM type (x86_64 or arm_64).
        - It specifies various VM settings, including:
            - Name of the VM
            - OS variant
            - CPU model
            - Number of virtual CPUs
            - Amount of RAM
            - Disk image file
            - Seed image for cloud-init
            - Network settings
            - Boot options (for ARM architecture)
        - The generated command can be executed in the terminal to set up the VM.
    """
    if vm_type.architecture == "x86_64":
        virshCommand = f'sudo virt-install --connect qemu:///system --import --virt-type qemu --name={name} --os-variant=ubuntu22.04 --cpu {vm_type.cpu_model} --vcpus={vm_type.num_cpus} --ram={vm_type.ram} --disk path=/home/cloud/resources/jammy-server-cloudimg-amd64.img,format=qcow2 --disk=/home/cloud/resources/seed.img,device=cdrom --network bridge=virbr0 --noautoconsole'
    elif vm_type.architecture == "arm_64":
        virshCommand = f'sudo virt-install --connect qemu:///system --import --virt-type qemu --name={name} --os-variant=ubuntu22.04 --arch aarch64 --boot uefi,loader=/home/cloud/resources/efi.img,loader_type=pflash,nvram_template=/home/cloud/resources/flash1.img --cpu {vm_type.cpu_model} --vcpus={vm_type.num_cpus} --ram={vm_type.ram} --disk path=/home/cloud/resources/jammy-server-cloudimg-arm64.img,format=qcow2 --disk=/home/cloud/resources/seed.img,device=cdrom --network bridge=virbr0 --noautoconsole'
    else:
        raise exceptions.Q8sFatalError(f"Unsupported architecture {vm_type.architecture}")
    print(f"Virsh command created: {virshCommand}")
    return virshCommand

def create_cloudimg_seed(path: str, public_key:str, vm_hostname: str, join_command: str):
    """
    Creates a cloud-init seed image for an Ubuntu cloud image.

    Args:
        path (str): The directory path where the seed image and metadata files will be created.
        public_key (str): The SSH public key to be injected into the VM for user access.
        vm_hostname (str): The hostname to be assigned to the virtual machine.
        join_command (str): The command to join the cluster, which will be included in the user data.
    """
    create_user_data(Path("/home/cloud/resources/user-data"), public_key, vm_hostname, join_command)
    create_meta_data(path)
    subprocess.run(f'cd {path}; cloud-localds seed.img user-data meta-data', shell=True)

def create_user_data(existing_udata: Path, public_key: str, vm_hostname: str, join_command: str):
    """
    Creates or modifies a user data file for cloud-init with SSH key and join command.

    Args:
        existing_udata (Path): The path to the existing user data file.
        public_key (str): The SSH public key to be added to the user data for authentication.
        vm_hostname (str): The hostname to be assigned to the virtual machine.
        join_command (str): The command for the VM to join the cluster, which will be included in the user data.

    Raises:
        exceptions.Q8sFatalError: If the base user data file cannot be found or accessed.

    Notes:
        - The original user data file is backed up with a `.bak` extension before being replaced with the modified version.
    """
    if not existing_udata.exists():
        subprocess.run(f"cp /home/cloud/Q8S/src/q8s/resources/user-data /home/cloud/resources", shell=True)
    if existing_udata.exists():
        with open(str(Path.home())+"/resources/user-data_new", "w") as new:
            with open(existing_udata, "r") as udata:
                #add ssh-key to user-creation
                insert_ssh = False
                insert_runcmd = False
                for l in udata.readlines():
                    if insert_ssh == True:
                        white = list(takewhile(str.isspace, l))
                        #write ssh key
                        new.write("".join(white) + "ssh_authorized_keys:\n" + "  ".join(white) + "- '" + public_key + "'\n")
                        insert_ssh = False
                        new.write(l)
                    elif " name:" in l:
                        new.write(l)
                        insert_ssh = True             
                    elif "runcmd:" in l:
                        new.write(l)
                        insert_runcmd = True
                    elif insert_runcmd == True:
                        white = list(takewhile(str.isspace, l))
                        #first install kubernetes
                        new.write(l)
                        #then add join-command execution
                        new.write("\n")
                        new.write("".join(white) + "- " + str(join_command.split(" ")) + "\n")
                        insert_runcmd = False
                    else: new.write(l)

            new.write(f"\nhostname: '{vm_hostname}'")
    else: raise exceptions.Q8sFatalError("cannot find user-data base for VMs")

    os.rename(existing_udata, os.path.dirname(existing_udata) + "/user-data.bak")
    os.rename(str(Path.home())+"/resources/user-data_new", str(Path.home())+"/resources/user-data")
    
def create_meta_data(path: str):
    """
    Creates an empty meta-data file for cloud-init to provide instance information.

    Args:
        path (str): The directory path where the meta-data file will be created.

    Raises:
        OSError: If there is an error writing the meta-data file.

    Notes:
        - The generated meta-data file will be named `meta-data` and placed in the specified directory.
        - The current implementation creates an empty file. Consider adding instance information as needed.
    """
    data = open(f"{path + '/meta-data'}", "w")
    #TODO ?

    data.close()

def create_arm_efi_and_nvram(destination_path: str):
    """
    Creates EFI and NVRAM images for ARM architecture.

    Args:
        destination_path (str): The directory path where the EFI and NVRAM images will be created.

    Notes:
        - The function uses `dd` to create zeroed images and populate the EFI image with QEMU firmware.
        - Ensures the created images are owned by the user 'cloud'.
    """
    subprocess.run(f"sudo dd if=/dev/zero of={destination_path + '/efi.img'} bs=1M count=64", shell=True)
    subprocess.run(f"sudo dd if=/usr/share/qemu-efi-aarch64/QEMU_EFI.fd of={destination_path + '/efi.img'} conv=notrunc; sudo chown cloud {destination_path + '/efi.img'}", shell=True)
    subprocess.run(f"sudo dd if=/dev/zero of={destination_path + '/flash1.img'} bs=1M count=64; sudo chown cloud {destination_path + '/flash1.img'}", shell=True)
    print("ARM EFI and flash memory created.")


if __name__ == "__main__":
    write_virsh_command()