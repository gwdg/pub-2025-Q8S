"""
Author: Vincent Hasse
Licence: MIT
"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger("logger")

@dataclass
class ClusterDefinition(yaml.YAMLObject):
    """Dataclass for Q8S cluster composition that can be parsed in YAML."""

    number_additional_master_nodes: int = 1
    master_node_flavor: str = "c1.small"
    worker: dict = field(default_factory=lambda:{"arm_mid" : 1, "x86_small" : 1})
    yaml_tag = "!ClusterDefinition"
    yaml_loader = yaml.SafeLoader

@dataclass
class VmType(yaml.YAMLObject):
    """Dataclass for VmType that can be parsed in YAML."""

    architecture: str = "x86"
    num_cpus: int = 2
    cpu_model: str = "EPYC-Rome"
    machine_model: str = "virt"
    ram: int = 2048
    storage: int = 10
    openstack_flavor: str = "c1.medium"
    yaml_tag = "!VmType"
    yaml_loader = yaml.SafeLoader

@dataclass
class VmTypes(yaml.YAMLObject):
    """Dataclass for dictionaries containing VmTypes that can be parsed in YAML."""

    types: dict = field(default_factory=lambda:{"x86_small": VmType(), "arm_mid": VmType(architecture="arm_64", num_cpus=6, cpu_model="cortex-a57", machine_model="virt", ram=4096, storage=20, openstack_flavor="c1.large")})
    yaml_tag = "!VmTypes"
    yaml_loader = yaml.SafeLoader

@dataclass
class ClusterData(yaml.YAMLObject):
    """Dataclass for Q8S Cluster descriptions that can be parsed in YAML."""

    git_url: str = "https://github.com/vhasse/Q8S.git"
    private_network_id: str = ""
    remote_ip_prefix: str = "10.254.1.0/24"
    default_image_name: str = "Ubuntu 22.04.4 Server x86_64 (ssd)"
    name_of_initial_instance: str = ""
    security_groups: list[str] = field(default_factory=lambda:[])
    required_tcp_ports: list[int] = field(default_factory=lambda:[])
    required_udp_ports: list[int] = field(default_factory=lambda:[])
    worker_port_range_min: int = 30000
    worker_port_range_max: int = 32767
    cluster_definition: ClusterDefinition = field(default_factory=ClusterDefinition)
    vm_types: list = field(default_factory=lambda:[])
    yaml_tag = "!ClusterData"
    yaml_loader = yaml.SafeLoader



def load_cluster_data(path: Path) -> ClusterData:
    """
    Loads cluster data from a YAML file and returns it as a ClusterData object.
    
    Args:
        path (Path): The file path to the cluster YAML configuration file.
        
    Returns:
        ClusterData: The cluster data object parsed from the YAML file.
        
    Raises:
        None explicitly, but logs messages if the YAML parsing fails or if the loaded data 
        is not of the expected type (ClusterData).
    """
    with open(path, "r", encoding="utf8") as file:
        try:
            cluster_data = yaml.safe_load(file)
        except yaml.YAMLError as exception:
            print(f"Parsing of cluster_config file failed with error: {exception}")
            print("Parsing of template failed with the following error:")
            print(exception)

        if not isinstance(cluster_data, ClusterData):
            logger.info("Could not parse yaml file as ClusterData. Make sure to use the template.")
            print("Could not parse yaml file as Deployment Configuration. Make sure to use the template.")
            logger.debug(f"Type of loaded yaml should be type DeployConfig but is type {type(cluster_data)}")
    return cluster_data



def get_worker_name(number: int, cluster_data: ClusterData) -> str:
    """
    Generates the name of a worker node in a Kubernetes cluster based on its number and the cluster configuration.
    
    Args:
        number (int): The worker node number for which the name is requested.
        cluster_data (ClusterData): The object containing the cluster's configuration data, including worker node definitions.

    Returns:
        str: The generated worker node name in the format 'worker-{number}-{VmType}'.
    
    Raises:
        IndexError: If the requested worker number exceeds the total number of workers defined in the cluster.

    """
    name = f"worker-{number}-"
    worker = cluster_data.cluster_definition.worker
    n = 0
    add = ""
    for k, v in worker.items():
        n += int(v)
        if n >= number:
            add = str(k)
            break
    if add == "":
        raise IndexError(f"Requested worker number is too high. Only {n} workers defined - asked for name for worker number {number}")
    name = name + add
    return name