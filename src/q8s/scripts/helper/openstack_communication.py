import base64
import logging
from pathlib import Path
import openstack
from openstack.connection import Connection
from openstack.config.loader import OpenStackConfig
import openstack.compute.v2.server as osserver
import os
from q8s.scripts.helper.cluster_def import ClusterData, VmType, VmTypes, get_worker_name
import q8s.scripts.helper.helper_functions
import q8s.scripts.helper.exceptions as exceptions
from keystoneauth1.exceptions import EndpointNotFound, SSLError, Unauthorized
from openstack.exceptions import ConflictException, SDKException


logger = logging.getLogger("logger")

def create_security_group(conn: openstack.connection.Connection, cluster_data: ClusterData) -> bool:
    """
    Creates a OpenStack security group for the Kubernetes cluster if it does not already exist, 
    and adds the required TCP and UDP rules based on the cluster configuration as well as an ICMP rule.

    Args:
        conn (openstack.connection.Connection): The OpenStack connection object used to interact with the OpenStack API.
        cluster_data (ClusterData): The configuration data of the Kubernetes cluster, containing required ports and other settings.

    Returns:
        bool: True if the security group was created or already exists, False if any errors were encountered.

    Raises:
        Q8sFatalError: If there is any error in creating the security group or adding rules.
    """
    sgroup_name = "q8s-cluster"
    security_groups = conn.list_security_groups()
    if sgroup_name in map(lambda key: key.get("name"), security_groups):
        logger.info(f"Security group with name {sgroup_name} already exists. Please check if the rules are appropriate.")
        return True
    
    try:
        conn.create_security_group(sgroup_name, f"Internal security group for q8s-cluster")
    except (ConflictException, SDKException) as exception:
        raise exceptions.Q8sFatalError(f"Error when trying to create new security group: {exception}")

    try:
        for tcp_port in cluster_data.required_tcp_ports:
            conn.create_security_group_rule(
                sgroup_name, tcp_port, tcp_port, "TCP", cluster_data.remote_ip_prefix
            )
    except (ConflictException, SDKException) as exception:
        logger.error()
        raise exceptions.Q8sFatalError(f"Error when adding rule [TCP, port: {tcp_port}] to security group: {exception}")
    try:
        for udp_port in cluster_data.required_udp_ports:
            conn.create_security_group_rule(
                sgroup_name, udp_port, udp_port, "UDP", cluster_data.remote_ip_prefix
            )
    except (ConflictException, SDKException) as exception:
        logger.error()
        raise exceptions.Q8sFatalError(f"Error when adding rule [UDP, port: {udp_port}] to security group: {exception}")
        
    try:
        conn.create_security_group_rule(
            sgroup_name,
            cluster_data.worker_port_range_min,
            cluster_data.worker_port_range_max,
            "TCP",
            cluster_data.remote_ip_prefix,
        )
    except (ConflictException, SDKException) as exception:
        logger.error()
        raise exceptions.Q8sFatalError(f"Error when adding rule [TCP, ports: {cluster_data.worker_port_range_min} - {cluster_data.worker_port_range_max}] to security group: {exception}")
    try:    
        conn.create_security_group_rule(
            sgroup_name,
            cluster_data.worker_port_range_min,
            cluster_data.worker_port_range_max,
            "UDP",
            cluster_data.remote_ip_prefix,
        )
    except (ConflictException, SDKException) as exception:
        logger.error()
        raise exceptions.Q8sFatalError(f"Error when adding rule [UDP, ports: {cluster_data.worker_port_range_min} - {cluster_data.worker_port_range_max}] to security group: {exception}")
    try:
        conn.create_security_group_rule(
            sgroup_name,
            direction='ingress',
            protocol='icmp',
            remote_ip_prefix='10.254.1.0/24',
            ethertype='IPv4'
        )
    except (ConflictException, SDKException) as exception:
        logger.error()
        raise exceptions.Q8sFatalError(f"Error when adding rule [ICMP, full subnet]] to security group: {exception}")


    logger.debug(f"Created Security group {sgroup_name}")
    return True


def calculate_free_resources(
    conn: openstack.connection.Connection,
    cluster_data: ClusterData
) -> bool:
    """Check whether compute limits can satisfy requested deployment and give an overview.

    Calls get openstack compute limits, as well as get openstack volume limits and calculates how many resources
    will be used by deploying the given number of master and worker nodes with the given flavors and volumes.
    Also displays an overview.

    Args:
        conn (openstack.connection.Connection): Valid openstack connection.
        cluster_data (q8s.scripts.helper.cluster_def.ClusterData): valid ClusterData
    Returns:
        bool: A bool that is true if the required resources fit within the maximum allowed compute limits
    """
    cluster_def = cluster_data.cluster_definition
    vm_types = VmTypes
    vm_types = cluster_data.vm_types
    compute_limits = get_openstack_compute_limits(conn)
    logger.debug(f"Received compute_limits: {compute_limits}")
    volume_limits = get_openstack_volume_limits(conn)
    logger.debug(f"Received volume_limits: {volume_limits}")
    master_node_flavor = conn.compute.find_flavor(cluster_data.cluster_definition.master_node_flavor)
    used_instances_after = compute_limits["used_instances"] + int(cluster_def.number_additional_master_nodes) 
    used_vcpus_after = compute_limits["used_cores"] + int(cluster_def.number_additional_master_nodes) * master_node_flavor.vcpus
    used_ram_after = compute_limits["used_ram"]+ int(cluster_def.number_additional_master_nodes) * master_node_flavor.ram
    used_volume_number_after = volume_limits["used_number"] + int(cluster_def.number_additional_master_nodes)
    used_volume_size_after = volume_limits["used_size"] + int(cluster_def.number_additional_master_nodes) * master_node_flavor.disk

    for w in cluster_def.worker:
        flav = conn.compute.find_flavor(vm_types.types[w].openstack_flavor)
        used_instances_after += cluster_def.worker[w]
        used_vcpus_after += flav.vcpus * cluster_def.worker[w]
        used_ram_after += flav.ram * cluster_def.worker[w]
        used_volume_number_after += 1 * cluster_def.worker[w]
        used_volume_size_after += flav.disk * cluster_def.worker[w]

    output = ""
    dash = "-" * 48
    output = output + "{:<12s}{:>12s}{:>12s}{:>12s}".format("Resource", "Used Now", "Used After", "Max") + "\n"
    output = output + dash + "\n"
    output = (
        output
        + "{:<12s}{:>12d}{:>12d}{:>12d}".format(
            "Instances", compute_limits["used_instances"], used_instances_after, compute_limits["max_instances"]
        )
        + "\n"
    )
    output = (
        output
        + "{:<12s}{:>12d}{:>12d}{:>12d}".format(
            "VCPUs", compute_limits["used_cores"], used_vcpus_after, compute_limits["max_cores"]
        )
        + "\n"
    )
    output = (
        output
        + "{:<12s}{:>12d}{:>12d}{:>12d}".format(
            "RAM", compute_limits["used_ram"], used_ram_after, compute_limits["max_ram"]
        )
        + "\n"
    )
    output = (
        output
        + "{:<12s}{:>12d}{:>12d}{:>12d}".format(
            "Volume size", volume_limits["used_size"], used_volume_size_after, volume_limits["max_size"]
        )
        + "\n"
    )
    output = (
        output
        + "{:<12s}{:>12d}{:>12d}{:>12d}".format(
            "Volumes", volume_limits["used_number"], used_volume_number_after, volume_limits["max_number"]
        )
        + "\n"
    )

    insufficient = False
    if used_instances_after > compute_limits["max_instances"]:
        logger.error("Not enough instances available to satisfy the requirements.")
        print("Not enough instances available to satisfy the requirements.")
        insufficient = True
    if used_vcpus_after > compute_limits["max_cores"]:
        logger.error("Not enough cores available to satisfy the requirements.")
        print("Not enough cores available to satisfy the requirements.")
        insufficient = True
    if used_ram_after > compute_limits["max_ram"]:
        logger.error("Not enough memory available to satisfy the requirements.")
        print("Not enough memory available to satisfy the requirements.")
        insufficient = True

    if used_volume_size_after > volume_limits["max_size"]:
        logger.error("Not enough volume size available to satisfy the requirements.")
        print("Not enough volume size available to satisfy the requirements.")
        insufficient = True
    if used_volume_number_after > volume_limits["max_number"]:
        logger.error("Not enough volumes available to satisfy the requirements.")
        print("Not enough volumes available to satisfy the requirements.")
        insufficient = True

    if insufficient:
        raise exceptions.Q8sFatalError("Due to unsatisfied requirements the process will terminate here.")

    logger.info("Enough resources are available to satisfy the requirements.")
    return True




def get_openstack_compute_limits(conn: openstack.connection.Connection) -> dict:
    """Makes a call to the openstack API for the compute limits, converts it into a dictionary and returns it.
    :param conn: A connection object initialized by create_openstack_connection.
    :type conn: openstack.connection.Connection
    :return: A dictionary containing the compute limits of the openstack account.
    :rtype: dict
    """
    limits = conn.get_compute_limits()
    limits_dict = {
        "max_cores": limits["max_total_cores"],
        "max_instances": limits["max_total_instances"],
        "max_ram": limits["max_total_ram_size"],
        "used_cores": limits["total_cores_used"],
        "used_instances": limits["total_instances_used"],
        "used_ram": limits["total_ram_used"],
    }
    return limits_dict




def get_openstack_volume_limits(conn: openstack.connection.Connection) -> dict:
    """Returns a dict with the volume limits for the given OpenStack connection.

    Args:
        conn (conn:openstack.connection.Connection): A connection object initialized by create_openstack_connection.

    Returns:
        dict: A dictionary containing the volume limits of the openstack account.
    """
    limits = conn.get_volume_limits()
    limits_dict = {
        "max_size": limits["absolute"]["maxTotalVolumeGigabytes"],
        "used_size": limits["absolute"]["totalGigabytesUsed"],
        "max_number": limits["absolute"]["maxTotalVolumes"],
        "used_number": limits["absolute"]["totalVolumesUsed"],
    }
    return limits_dict



def create_keypair(conn):
    """
    Creates or retrieves an existing SSH keypair for an OpenStack cluster, saves the keypair locally, and sets appropriate permissions.
    compare: https://docs.openstack.org/openstacksdk/latest/user/guides/compute.html

    Args:
        conn (openstack.connection.Connection): The OpenStack connection object used to interact with the OpenStack API.

    Returns:
        object: The keypair object created or retrieved from OpenStack.

    Description:
        - Checks if an SSH keypair named "q8s-cluster" already exists in OpenStack. 
        - If it exists, it logs the key details and saves the public key locally to `~/.ssh/q8s-cluster.pub` if it doesn't already exist.
        - If it does not exist, the function creates a new keypair in OpenStack and saves both the private and public keys to the local `~/.ssh/` directory.
        - The function ensures that the correct permissions (600) are applied to the keys.
        - Raises a `Q8sFatalError` if the `.ssh` directory cannot be created or if there is an issue writing the keypair files.
    """
    
    NAME = "q8s-cluster"
    keypair = conn.compute.find_keypair(NAME)

    if keypair:
        logger.info(f"SSH key '{NAME}' already exists. Public key:\n{keypair.public_key}\n")
        if not Path(Path.home().joinpath(f".ssh/{NAME}.pub")).is_file():
            with open(Path.home() / ".ssh" / (NAME + ".pub") , 'w') as f:
                f.write("%s" % keypair.public_key)
        else: logger.debug(f"Using public key:\n{open(Path.home() / '.ssh' / (NAME + '.pub'), 'r').read()}")

    if not keypair:
        logger.info(f"Creating Key Pair: {NAME}")

        keypair = conn.compute.create_keypair(name=NAME)
        try:
            if not(os.path.exists(Path.home() / ".ssh")):
                os.mkdir(Path.home() / ".ssh")
        except OSError as e:
            logger.error("Cannot create .ssh directory.")
            raise exceptions.Q8sFatalError("Cannot save private SSH key to ~/.ssh/ - cannot create directory.")
        try:
            with open(Path.home() / ".ssh" / NAME, 'w') as f:
                f.write("%s" % keypair.private_key)

            with open(Path.home() / ".ssh" / (NAME + ".pub") , 'w') as f:
                f.write("%s" % keypair.public_key)
        except Exception as e:
            logger.error(f"Could not write ssh keypair in ~/.ssh/\nException: {e}")
            raise exceptions.Q8sFatalError(f"Cannot save SSH key to ~/.ssh/. Does a file with the name 'q8s-cluster' or 'q8s-cluster.pub' already exist in that directory?\n Exiting due to potential mismatch of SSH keys.")

        os.chmod(Path.home() / ".ssh" / NAME, 0o600)
        os.chmod(Path.home() / ".ssh" / (NAME + ".pub"), 0o600)
    
    return keypair


def create_openstack_connection_from_file(path: Path) -> Connection:
    """
    Creates an OpenStack connection using the credentials from a specified configuration file (cloud.yaml).

    Args:
        path (Path): The file path to the cloud configuration file (typically a `cloud.yaml` file).

    Returns:
        openstack.connection.Connection: An OpenStack connection object initialized with the credentials from the file.

    Raises:
        Q8sFatalError: If the connection to OpenStack cannot be established or if the connection verification fails.
    """
    os.environ["OS_CLIENT_CONFIG_FILE"] = str(path)
    logger.debug("connecting to Openstack")
    try:
        cloud_name = "openstack"
        conn = openstack.connect(cloud=cloud_name)
    except Exception:
        print("Cannot connect to cloud {cloud_name}. Make sure it exists in your cloud.yaml")
        logger.error("Cannot connect to cloud {cloud_name}. Make sure it exists in your cloud.yaml")
        raise exceptions.Q8sFatalError(f"Cannot connect to cloud {cloud_name}. Make sure it exists in your cloud.yaml")
    
    if not verify_openstack_connection(conn):
        raise exceptions.Q8sFatalError(
            f"Openstack verification failed. Could not access Openstack API with the"
            f" given credentials.\n"
            f"Please verify that your credentials and the given url are correct."
        )
    return conn

def verify_openstack_connection(conn: openstack.connection.Connection) -> bool:
    """
    Verifies the connection to the OpenStack API by checking the compute limits.

    Args:
        conn (openstack.connection.Connection): An OpenStack connection object.

    Returns:
        bool: True if the connection is valid, False otherwise.
    """
    try:
        _ = conn.get_compute_limits()
    except Unauthorized as _:
        logger.error("Authentication with Openstack failed, please verify your credentials.")
        return False
    except EndpointNotFound as _:
        logger.error("Authentication Endpoint not found, make sure the auth url is correct.")
        return False
    except SSLError as _:
        logger.error("SSL Error, make sure the auth url is correct.")
        return False
    logger.debug("Connection to Openstack is valid.")
    return True


def add_security_group_to_initial_instance(openstack_conn: openstack.connection.Connection, cluster_data: ClusterData):
    """
    Adds the initial instance specified in the cluster data to the 'q8s-cluster' security group.

    Args:
        openstack_conn (openstack.connection.Connection): An OpenStack connection object used to interact with the OpenStack API.
        cluster_data (ClusterData): An object containing cluster configuration data, including the name of the initial instance.
    """
    logger.debug(f"Adding init instance with name {cluster_data.name_of_initial_instance} to q8s-cluster security group.")
    server = openstack_conn.compute.find_server(cluster_data.name_of_initial_instance)
    security_group = openstack_conn.network.find_security_group('q8s-cluster')
    try:
        if not any(sg['name'] == 'q8s-cluster' for sg in server.security_groups):
            openstack_conn.compute.add_security_group_to_server(server, security_group)
    except Exception as e:
        logger.error("Could not add initial instance to security group 'q8s-cluster'. Did you specify the correct instance name in the cluster definition file?")



def spawn_openstack_instances(openstack_conn: openstack.connection.Connection, cluster_data: ClusterData) -> dict[str, list[openstack.compute.v2.server.Server]]:
    """
    Spawns OpenStack instances based on the provided cluster configuration and returns a dictionary containing the created server instances.

    Args:
        openstack_conn (openstack.connection.Connection): An OpenStack connection object used to interact with the OpenStack API.
        cluster_data (ClusterData): An object containing configuration data for the cluster, including network and instance details.

    Returns:
        dict[str, list[openstack.compute.v2.server.Server]]: A dictionary where keys are instance types ('master' and 'worker') and values are lists of created server instances of type `openstack.compute.v2.server.Server`.
    """
    servers = {}
    logger.info("Spawning OpenStack instances...")
    keypair = create_keypair(openstack_conn)
    create_security_group(openstack_conn, cluster_data)
    add_security_group_to_initial_instance(openstack_conn, cluster_data)
    #print("private network id: " + cluster_data.private_network_id)
    network = openstack_conn.network.find_network(cluster_data.private_network_id)
    if network is None:
        logger.error(f"Could not find valid subnet id for private network:{cluster_data.private_network_id}")
        raise exceptions.Q8sFatalError(
            f"Could not find valid subnet id for private network:"
            f" {cluster_data.private_network_id}")

    servers["master"] = spawn_master_nodes(cluster_data, openstack_conn, keypair, network)
    servers["worker"] = spawn_worker_nodes(cluster_data, openstack_conn, keypair, network)

    # wait for servers to get their IP assigned
    logger.info("Waiting for OpenStack instances...")
    for l in servers.values():
        for server in l:
            openstack_conn.compute.wait_for_server(server)
    logger.info("All servers created.")
    
    return servers



def spawn_master_nodes(cluster_data: ClusterData, conn: Connection, keypair, network) -> list[openstack.compute.v2.server.Server]:
    """
    Spawns master nodes in OpenStack based on the provided cluster configuration and returns a list of created server instances.

    Args:
        cluster_data (ClusterData): An object containing configuration data for the cluster, including node specifications, image names, and security groups.
        conn (Connection): An OpenStack connection object used to interact with the OpenStack API.
        keypair: The SSH keypair to be associated with the created server instances.
        network: The network in which the master nodes will be created.

    Returns:
        list[openstack.compute.v2.server.Server]: A list of created server instances of type `openstack.compute.v2.server.Server`.
    """
    servers = []
    if cluster_data.cluster_definition.number_additional_master_nodes > 0:
        try:
            image = conn.image.find_image(cluster_data.default_image_name)
            flavor = conn.compute.find_flavor(cluster_data.cluster_definition.master_node_flavor)
            user_data = base64.b64encode(f"#!/bin/bash\ncd ~\nsudo apt install -y git\ngit clone {cluster_data.git_url}".encode("utf-8")).decode('utf-8')
            sec_groups = []
            for n in cluster_data.security_groups:
                sec_groups.append({'name': f'{n}'})
            logger.debug("Resources ready")
            for i in range(cluster_data.cluster_definition.number_additional_master_nodes):
                name = "master-" + str(i+1)
                server = conn.compute.create_server(
                    name=name,
                    image_id=image.id,
                    flavor_id=flavor.id,
                    networks=[{"uuid": network.id}],
                    key_name=keypair.name,
                    user_data=user_data,
                    security_groups=sec_groups
                )
                logger.debug(f"Server {server.name} created.")
                servers.append(server)

            logger.info("Master nodes created.")
        except Exception as e:
            print(e)
            logger.error("Cannot create server: " + str(e.with_traceback()))
            raise exceptions.Q8sFatalError("Cannot create server: " + str(e))
        
    return servers



def spawn_worker_nodes(cluster_data: ClusterData, conn: Connection, keypair, network) -> list[openstack.compute.v2.server.Server]:
    """
    Spawns worker nodes in OpenStack based on the provided cluster configuration and returns a list of created server instances.

    Args:
        cluster_data (ClusterData): An object containing configuration data for the cluster, including node specifications, image names, and security groups.
        conn (Connection): An OpenStack connection object used to interact with the OpenStack API.
        keypair: The SSH keypair to be associated with the created server instances.
        network: The network in which the worker nodes will be created.

    Returns:
        list[openstack.compute.v2.server.Server]: A list of created server instances of type `openstack.compute.v2.server.Server`.
    """
    logger.debug("Creating worker nodes")
    servers = []
    workers = cluster_data.cluster_definition.worker
    worker_number = 0
    total = 0
    try:
        image = conn.image.find_image(cluster_data.default_image_name)
        sec_groups = []
        for n in cluster_data.security_groups:
            sec_groups.append({'name': f'{n}'})
        user_data = base64.b64encode(f"#!/bin/bash\ncd ~\nsudo apt install -y git\ngit clone {cluster_data.git_url}".encode("utf-8")).decode('utf-8')

        for vm_type, number in workers.items():
            flavor = conn.compute.find_flavor(cluster_data.vm_types.types[vm_type].openstack_flavor)
            logger.debug("Resources ready")
            total += int(number)
            for i in range(number):
                if (worker_number+1) <= total:
                    worker_number += 1
                    name = get_worker_name(worker_number, cluster_data)
                    server = conn.compute.create_server(
                        name=name,
                        image_id=image.id,
                        flavor_id=flavor.id,
                        networks=[{"uuid": network.id}],
                        key_name=keypair.name,
                        user_data=user_data,
                        security_groups=sec_groups
                    )
                    logger.debug(f"Server {server.name} created.")
                    servers.append(server)

        logger.info("Worker nodes created.")
    except Exception as e:
        print(e)
        logger.error("Cannot create server: " + str(e.with_traceback()))
        raise exceptions.Q8sFatalError("Cannot create server: " + str(e))

    return servers