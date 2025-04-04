# Q8S

This repository contains the source code for the Q8S prototype implementation.
It uses [QEMU](https://qemu.org/) and [libvirt](https://libvirt.org/) to create emulated Kubernetes nodes in an OpenStack environment
to emulate heterogeneous Kubernetes clusters for the purpose of research and development of scheduling solutions for heterogeneous clusters.

Given a cluster specification and OpenStack application credentials, Q8S will
- request nodes from OpenStack
- initialize a Kubernetes cluster on the first node
- install Kubernetes on the other control plane nodes
- prepare QEMU on the worker nodes to emulate the desired hardware
- let the worker nodes running on emulated hardware join the cluster

## Installation

Q8S is to be used in an OpenStack environment, please make sure that sufficient resources are available in your
OpenStack project for the cluster that you want to create.
Q8S expects to be installed on one of the OpenStack nodes, which will be used as the first control plane node.

To install Q8S, please complete the following steps:
- Deploy an OpenStack VM running Ubuntu (22.04 or newer recommended) and name it `q8s-master`
- Connect to the VM per SSH
- Install git and python3-poetry `sudo apt update && sudo apt install -y git python3-poetry`
- Clone the Q8S repository `git clone https://github.com/gwdg/pub-2025-q8s.git`
- Change into the Q8S directory `cd pub-2025-q8s`
- `poetry config virtualenvs.in-project true`
- `poetry install`
- `source .venv/bin/activate`
- Open the OpenStack Horizon web interface and navigate to Identity and Application Credentials, create a new credential and download them as `clouds.yaml`
- Copy the `clouds.yaml` file to the Q8S directory
- In the OpenStack Horizon web interface navigate to Networks and Network and find the private network, open it and copy its ID
- Edit the `cluster.yaml` file, set the `private_network_id` to the ID of the private network

After completing these steps you are ready to use Q8S to deploy a cluster by configuring the `cluster.yaml` file
and running `q8s deploy clouds.yaml cluster.yaml`.

## Usage

Configure `cluster.yaml` according to your needs and run `q8s deploy clouds.yaml cluster.yaml` to start the deployment.
Upon completion, the specified heterogeneous Kubernetes cluster will be ready for usage via kubectl as Q8S automatically sets up the kubeconfig file.

See the following table for configuring the `cluster.yaml` file:

| Parameter                      | Description                                                                                                  |
|--------------------------------|--------------------------------------------------------------------------------------------------------------|
| git_url                        | URL to a Q8S repository for downloading scripts on the deployed nodes                                        |
| private_network_id             | ID of the private OpenStack network used in the OpenStack project                                            |
| remote_ip_prefix               | IP range of the OpenStack network in CIDR notation, /24 network expected                                     |
| default_image_name             | Name of the OpenStack image to use for the host instances, should be an Ubuntu image                         |
| name_of_initial_instance       | Name of the instance (in OpenStack) on which Q8S is started, default is "q8s-master"                         |
| security_groups                | Security groups that should be added to the OS instances. Required: "q8s-cluster" (should not already exist) |
| required_tcp_ports             | TCP ports that should be added to the "q8s-cluster" security group, defaults should be kept                  |
| required_udp_ports             | UDP ports that should be added to the "q8s-cluster" security group, defaults should be kept                  |
| worker_port_range_min          | Minimum port number for the worker port range, will be opened via security group and used for K8s worker     |
| worker_port_range_max          | Maximum port number for the worker port range, will be opened via security group and used for K8s worker     |
| master_node_flavor             | Name of the OpenStack flavor to use for the master node                                                      |
| number_additional_master_nodes | Number of additional master nodes to deploy, these nodes will deploy without QEMU                            |
| worker                         | Specify vm_types and set the number to deploy for each here                                                  |
| vm_types                       | Fill out the dictionary to specify a new worker node type                                                    |
| architecture                   | System architecture of the nodes, currently only "x86_64" and "arm_64" are supported                         |
| num_cpus                       | Number of VCPUs                                                                                              |
| cpu_model                      | Name of the CPU model as listed in QEMU documentation. Has to match the architecture!                        |
| machine_model                  | Name of the machine model. Should always be "virt"                                                           |
| ram                            | RAM in MB                                                                                                    |
| storage                        | Storage in GB                                                                                                |
| openstack_flavor               | OpenStack flavor to use for the host. Must have enough compute power to support the VM-type                  |


## How it works

Q8S deploy QEMU on top of the OpenStack VMs it requests for a given cluster configuration.
It then uses Ubuntu Cloud-Images for the requested architecture to prepare VM images for QEMU and deploys them.
Via cloud-init scripts, Kubernetes is installed and configured within the QEMU VMs.
To join all the nodes together, Q8S configures iptables such that any traffic sent 
to the OpenStack VM is redirected to the internal QEMU VM using NAT rules.
The exceptions to this are port 22, which still provides SSH access to the OpenStack host and port 2222, which redirects
to port 22 of the QEMU VM for SSH access.