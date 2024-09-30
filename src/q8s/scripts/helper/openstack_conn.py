"""
Author: Vincent Hasse
License: MIT
Some parts are taken from the Ironik project of Jonathan Decker (under MIT license):
https://gitlab-ce.gwdg.de/jdecker/ironik

"""
import openstack
from keystoneauth1.exceptions import EndpointNotFound, SSLError, Unauthorized
import q8s.scripts.helper.exceptions as exceptions
import getpass
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import logging

logger = logging.getLogger("logger")

@dataclass
class OpenStackCredentials(yaml.YAMLObject):
    """Dataclass for OpenStack credentials that can be parsed in YAML."""

    username: str = ""
    password: str = ""
    project_id: str = ""
    yaml_tag = "!OpenStackCredentials"
    yaml_loader = yaml.SafeLoader

@dataclass
class OpenStackConfig(yaml.YAMLObject):
    """Dataclass for OpenStack configuration that can be parsed in YAML."""

    openstack_auth_url: str = ""
    user_domain_name: str = ""
    project_domain_name: str = ""
    lb_provider: str = ""
    default_flavor_name: str = ""
    default_image_name: str = ""
    remote_ip_prefix: str = ""
    private_network_id: str = ""
    region_name: str = "RegionOne"
    use_octavia: bool = False
    security_group_name: str = "ironik-k8s-node"
    volume_size: int = 20
    # volume_type: str = "ssd"
    yaml_tag = "!OpenStackConfig"
    yaml_loader = yaml.SafeLoader

@dataclass 
class OpenStackAuth(yaml.YAMLObject):
    version: str = ""
    username: str = ""
    password: str = ""
    project_id: str = ""
    auth_url: str = ""
    yaml_tag = "!OpenStackAuth"
    yaml_loader = yaml.SafeLoader

@dataclass
class OpenStackData(yaml.YAMLObject):
    openstack_credentials: OpenStackCredentials = field(default_factory=OpenStackCredentials)
    openstack_config: OpenStackConfig = field(default_factory=OpenStackConfig)
    yaml_tag = "!OpenStackData"
    yaml_loader = yaml.SafeLoader


def load_openstack_data(path: Path) -> OpenStackData:
    with open(path, "r", encoding="utf-8") as file:
        try:
            openstack_data = yaml.safe_load(file)
        except yaml.YAMLError as exception:
            print(f"Parsing of yaml file failed with error: {exception}")
            print("Parsing of template failed with the following error:")
            print(exception)
        
        if not isinstance(openstack_data, OpenStackData):
            logger.info("Could not parse yaml file as Deployment Configuration. Make sure to use the template.")
            print("Could not parse yaml file as Deployment Configuration. Make sure to use the template.")
            logger.debug(f"Type of loaded yaml should be DeployConfig but is {type(OpenStackData)}")
    return openstack_data

def create_openstack_connection(
    username: str,
    password: str,
    project_id: str,
    auth_url: str,
    region_name: str,
    user_domain_name: str,
    project_domain_name: str,
) -> openstack.connection.Connection:
    """Creates an openstack.connection.Connection object based on the given credentials and further information from
    gwdg_defaults. This alone does not validate any of the credentials.
    This is the base object for all API calls to Openstack using the openstacksdk.
    Docs can be found here: https://docs.openstack.org/openstacksdk/latest/user/connection.html
    :param username: Openstack username.
    :type username: str
    :param password: Openstack password.
    :type password: str
    :param project_id: Openstack project id for which this tool should run.
    :type project_id: str
    :param auth_url: Openstack authentication url, which should be the identity service url followed by /v3.
    :type auth_url: str
    :return: A connection object from the openstacksdk.
    :rtype: openstack.connection.Connection
    :param region_name:
    :param user_domain_name:
    :param project_domain_name:
    """
    conn = openstack.connection.Connection(
        region_name=region_name,
        auth=dict(
            auth_url=auth_url,
            username=username,
            password=password,
            project_id=project_id,
            user_domain_name=user_domain_name,
            project_domain_name=project_domain_name,
        ),
    )
    return conn


def verify_openstack_connection(conn: openstack.connection.Connection) -> bool:
    """Verifies that the openstack connection is valid by making a simple API call.
    Returns True if it is valid and false otherwise.
    :param conn: A connection object initialized by create_openstack_connection.
    :type conn: openstack.connection.Connection
    :return: True if the connection is valid and false otherwise.
    :rtype: bool
    """
    try:
        _ = conn.get_compute_limits()
    except Unauthorized as _:
        print("Authentication with Openstack failed, please verify your credentials.")
        return False
    except EndpointNotFound as _:
        print("Authentication Endpoint not found, make sure the auth url is correct.")
        return False
    except SSLError as _:
        print("SSL Error, make sure the auth url is correct.")
        return False
    logger.debug("Connection to Openstack is valid.")
    return True


def create_and_test_openstack_connection(
    openstack_credentials: OpenStackCredentials, openstack_config: OpenStackConfig
) -> openstack.connection.Connection:
    """Call create openstack connection and communicates possible errors.
    :param openstack_credentials:
    :param openstack_config:
    """
    # passsword check for openstack
    openstack_credentials = check_openstack_password(openstack_credentials)

    conn = create_openstack_connection(
        openstack_credentials.username,
        openstack_credentials.password,
        openstack_credentials.project_id,
        openstack_config.openstack_auth_url,
        openstack_config.region_name,
        openstack_config.user_domain_name,
        openstack_config.project_domain_name,
    )
    if not verify_openstack_connection(conn):
        raise exceptions.IronikFatalError(
            f"Openstack verification failed. Could not access Openstack API with the"
            f" given credentials under {openstack_config.openstack_auth_url}.\n"
            f"Please verify that your credentials and the given url are correct."
        )
    logger.debug("Openstack verification successful.")

    return conn


def check_openstack_password(openstack_credentials: OpenStackCredentials) -> OpenStackCredentials:
    """Check if password is available in openstack_config.yaml or not.
    If not available ask user from command line.
    :param openstack_credentials: object contains data for openstack connection
    :type openstack_credentials: OpenStackCredentials
    :return openstack_credentials: object contains data for openstack connection with password
    :type openstack_credentials: OpenStackCredentials
    """
    if openstack_credentials.password == "":
        logger.info("Password for openstack is not available.")
        print("Password for openstack is not available.\n")
        password = getpass.getpass(prompt="Enter Password:")
        openstack_credentials.password = password

    return openstack_credentials
