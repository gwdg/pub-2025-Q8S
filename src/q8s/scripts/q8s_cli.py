import logging
import sys
from q8s.scripts import initialize_setups, install_guest
from q8s.scripts.helper import helper_functions
from q8s.scripts.helper import exceptions, openstack_communication
from q8s.scripts.helper.openstack_conn import create_and_test_openstack_connection, load_openstack_data
from q8s.scripts.helper.cluster_def import load_cluster_data, ClusterDefinition, ClusterData
from q8s.scripts.helper import kubernetes_helper
from q8s.scripts import routing_master
from pathlib import Path
import click
import subprocess
import multiprocessing
from q8s.scripts.helper.q8s_logger import setup_logger
import time


logger = logging.getLogger("logger")


@click.group()
@click.option("-v", "--verbose", "--debug", is_flag=True, default=False, help="Enable verbose debug logging.")
def q8s_cli(verbose=False):
    if verbose:
        print("Running in verbose mode, extensive logging is active.")
        setup_logger(console_level=logging.DEBUG, log_file_level=logging.DEBUG)
    else:
        setup_logger(console_level=logging.INFO, log_file_level=logging.INFO)

    if verbose:
        logger.debug("Running in verbose mode, extensive logging is active.")



@q8s_cli.command(name="deploy",
                 short_help="Create a new Kubernetes Cluster based on the cluster_config file.\n Uses the Openstack account specified in the openstack_conf.yaml")
@click.argument("openstack_conf_file", type=click.Path(path_type=Path), required=True)
@click.argument("cluster_data_file", type=click.Path(path_type=Path), required=True)
@click.option("-d", "--dry-run", is_flag=True, default=False, help="Start dry-run, no data will be written.")
def deploy(openstack_conf_file: Path, cluster_data_file: Path, dry_run: bool) -> None:
    """:param name: openstack authentication file -> e.g. clouds.yaml from Openstack Dashboard with username and password fields added
    :param name: cluster definition file
    :return:
    """
    logger.debug(f"Cluster initialization started with files: OpenstackAuthentication: {openstack_conf_file}, ClusterDefinition: {cluster_data_file}")

    try:
        #get Openstack config
        if not openstack_conf_file.is_file():
            print(f"Path to openstack_config_file is not valid: {openstack_conf_file.absolute}")
            logger.info(f"Path to openstack_config_file is not valid: {openstack_conf_file.absolute}")
            raise exceptions.Q8sFatalError(f"Path to openstack_config_file is not valid: {openstack_conf_file.absolute}")   
        #openstack.enable_logging(debug=True)
        conn = openstack_communication.create_openstack_connection_from_file(openstack_conf_file)
        cluster_data = load_cluster_data(cluster_data_file)
        #resource calculation/checking
        openstack_communication.calculate_free_resources(conn, cluster_data)
        if dry_run:
            print("End of dry run.")
            logger.debug("End of dry run.")
            return

        # launch all OpenstackInstances
        servers = openstack_communication.spawn_openstack_instances(conn, cluster_data)
        
        #TODO:let it run in parallel
        #automatically select default option in case of conflicts with configuration files 
        subprocess.run("sudo apt upgrade -y -o Dpkg::Options::='--force-confdef' -o Dpkg::Options::='--force-confold'", shell=True)
        logger.info("Installing kubernetes...")
        result = subprocess.run("bash /home/cloud/Q8S/src/q8s/scripts/install-k8s.sh", capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            logger.error(f"Could not install Kubernetes on the initializing instance. Stderr: {result.stderr}")
            raise exceptions.Q8sFatalError(f"Could not install Kubernetes on the initializing instance. Stderr: {result.stderr}")
        logger.info("Initializing kubernetes cluster...")
        result = subprocess.run("bash /home/cloud/Q8S/src/q8s/scripts/setup-kube-ctl.sh", capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            logger.error(f"Could not initialize Kubernetes Cluster. Stderr: {result.stderr}")
            raise exceptions.Q8sFatalError(f"Could not initialize Kubernetes Cluster. Stderr: {result.stderr}")

        # save IPs of worker and master instances
        worker_nodes = {}
        master_nodes = {}
        for s in servers["worker"]:
            worker_nodes[s.name] = s.addresses[conn.network.find_network(cluster_data.private_network_id).name][0]['addr']
        for s in servers["master"]:
            master_nodes[s.name] = s.addresses[conn.network.find_network(cluster_data.private_network_id).name][0]['addr']
        logger.debug(f"Worker: {worker_nodes}\nMaster: {master_nodes}")
        
        #create routing rules 
        logger.info("Creating routing rules.")
        routing_master.create_master_routing(worker_nodes.values())
        #make them persistent
        subprocess.run("bash /home/cloud/Q8S/src/q8s/scripts/helper/make_master_routing_persistent.sh", shell=True)

        logger.info("Sending cluster info to workers.")
        helper_functions.send_file_via_sftp(worker_nodes.values(), str(cluster_data_file), "/home/cloud/resources/cluster.yaml")
        helper_functions.send_file_via_sftp(worker_nodes.values(), "/home/cloud/.ssh/q8s-cluster.pub", "/home/cloud/resources/q8s-cluster.pub")
        #different join command for workers and master nodes
        helper_functions.send_file_via_sftp(worker_nodes.values(), "/home/cloud/resources/join_command_worker.txt", "/home/cloud/resources/join_command.txt")
        helper_functions.send_file_via_sftp(master_nodes.values(), "/home/cloud/resources/join_command_master.txt", "/home/cloud/resources/join_command.txt")

        #send worker_nodes to master nodes
        with open("/home/cloud/resources/worker_ips.txt", "w", encoding='utf-8') as f:
            f.write(str(list(worker_nodes.values())))
        with open("/home/cloud/resources/master_ips.txt", "w", encoding='utf-8') as f:
            f.write(str(list(master_nodes.values())))
        helper_functions.send_file_via_sftp(master_nodes.values(), "/home/cloud/resources/worker_ips.txt", "/home/cloud/resources/worker_ips.txt")

        #start host-setups in parallel
        logger.debug(f"Starting init_host_setup for workers with servers: {worker_nodes}")
        processes = []
        for ip in worker_nodes.values():
            processes.append(multiprocessing.Process(target=initialize_setups.init_host_setup, args=[ip,]))
        for ip in master_nodes.values():
            processes.append(multiprocessing.Process(target=initialize_setups.init_master_setup, args=[ip,]))
        for p in processes:
            p.start()
        logger.info("Setups started. Waiting for callbacks... this might take some time (15+ min)")
        #wait for setups to finish
        for p in processes:
            p.join()
        #copy kube-config to master nodes
        helper_functions.send_file_via_sftp(master_nodes.values(), "/home/cloud/.kube/config", "/home/cloud/.kube/config")
        logger.info("Host setups finished. VMs booting. Waiting for nodes to join the cluster... This might take some time (30min+)")

        cluster_nodes = {}
        for k, v in master_nodes.items():
            cluster_nodes[k] = v
        for k, v in worker_nodes.items():
            cluster_nodes["vm-"+str(k)] = v
        all_joined = False
        elapsed = 0
        #wait for all nodes to join the cluster
        while not all_joined:
            time.sleep(60)
            elapsed += 1
            all_joined, missing_nodes, not_ready_nodes = kubernetes_helper.check_joined_nodes(set(cluster_nodes.keys()))
            logger.debug(f"Waiting for nodes {missing_nodes} to join the cluster.")
            if all_joined:
                logger.info("All nodes have joined the cluster. Setting up networking.")
                for name, ip in cluster_nodes.items():
                    #annotate nodes for Flannel communication using public-ip
                    annotations = {
                        "flannel.alpha.coreos.com/public-ip": f"{ip}",
                        "flannel.alpha.coreos.com/public-ip-overwrite": f"{ip}"
                    }
                    result = kubernetes_helper.annotate_node(name, annotations)
                    if result:
                        logger.debug(f"Node {name} annotated with {annotations}")
                    else: logger.error(f"Node {name} could not be annotated. This will affect networking. Please annotate the node by hand with {annotations}.")
                logger.debug("Restarting Flannel daemonset...")
                result = subprocess.run("kubectl rollout restart daemonset kube-flannel-ds -n kube-flannel", capture_output=True, text=True, shell=True)
                if result.returncode != 0:
                    logger.warning(f"Could not restart Flannel daemonset. Please check, if cluster communication works. Try restarting it by executing 'kubectl rollout restart daemonset kube-flannel-ds -n kube-flannel'.\nSdterr: {result.stderr}")
            elif elapsed > 40:
                logger.info(f"{elapsed} minutes have passed since the setup for the VMs has been initialized. Nodes {missing_nodes} are missing. There may be something wrong. You can check the VM status by opening a new console, SSH to the host and run 'sudo virsh list'. It should list the VM as started. For further information you can open a console with 'sudo virsh console <vm-name>'.")
        if len(not_ready_nodes) > 0:
            logger.info(f"Nodes {not_ready_nodes} are not showing 'Ready' state. Check if the problem persists after ~1min using 'kubectl get nodes'. I it does persist you can use 'kubectl describe node <node-name>' to get more information about the node's state.")

    except exceptions.Q8sFatalError as exception:
        print(exception)
        print("Exiting application - no cleanup yet!")
        logger.critical("exiting application - no cleanup yet!")
        logger.critical(exception)
        sys.exit(1)
        
    logger.info("Q8S setup finished. You can check the nodes of the cluster using 'kubectl get nodes'.")

