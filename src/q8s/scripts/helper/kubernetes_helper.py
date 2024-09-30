"""
Author: Vincent Hasse
Licence: MIT
"""
from kubernetes import config, client

def check_joined_nodes(expected_nodes: set):
    """
    Checks if the expected nodes have joined the Kubernetes cluster and if they are in the 'Ready' state.

    Args:
        expected_nodes (set): A set of node names that are expected to be in the cluster.

    Returns:
        tuple:
            - bool: True if all expected nodes are present and in the 'Ready' state, False otherwise.
            - list[str]: A list of missing node names (nodes that have not joined).
            - list[str]: A list of node names that are not in the 'Ready' state.
    """
    config.load_kube_config()
    api_client = client.CoreV1Api()
    nodes = api_client.list_node().items
    #extract node names
    curr_nodes = set(node.metadata.name for node in nodes)

    missing_nodes = expected_nodes - curr_nodes
    not_ready_nodes = []

    #check if all nodes are in ready state
    for node in nodes:
        node_name = node.metadata.name
        if node_name in expected_nodes:
            # Find the "Ready" condition for the node
            conditions = node.status.conditions
            ready_condition = next((cond for cond in conditions if cond.type == "Ready"), None)
            if not ready_condition or ready_condition.status != "True":
                not_ready_nodes.append(node_name)

    if not missing_nodes and not not_ready_nodes:
        return True, [], []
    else:
        return False, list(missing_nodes), not_ready_nodes
    
def annotate_node(node_name: str, annotations: dict) -> bool:
    """
    Adds or updates annotations on a Kubernetes node.

    Args:
        node_name (str): The name of the node to annotate.
        annotations (dict): A dictionary of annotations to be added or updated on the node.

    Returns:
        bool: True if the annotations were successfully applied, False if there was an error.
    """
    config.load_kube_config()
    api_client = client.CoreV1Api()
    # patch with new annotations
    body = {
        "metadata": {
            "annotations": annotations
        }
    }
    try:
        result = api_client.patch_node(node_name, body)
        return True
    except client.ApiException.ApiException as e:
        return False