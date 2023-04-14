import logging
import os

import click
import requests
import yaml

import docker

giskard_home_path = os.path.expanduser("~/giskard-home")
giskard_settings_path = giskard_home_path + "/giskard-settings.yml"

client = docker.from_env()

logger = logging.getLogger(__name__)


@click.group("server", help="Giskard UI management", context_settings={"show_default": True})
def server() -> None:
    """
    Giskard UI management
    """


def start_options(fn):
    fn = click.option(
        "--attach",
        "-a",
        "attached",
        is_flag=True,
        default=False,
        help="Starts the server and attaches to it, displaying logs in console.",
    )(fn)
    return fn


def update_options(fn):
    fn = click.option(
        "--version",
        "-v",
        "version",
        is_flag=False,
        default="",
        help="Version to update to."
    )(fn)
    return fn


@server.command("start")
@start_options
def start(attached):
    """\b
    Start Giskard Server.

    By default, the server starts detached and will run in the background.
    You can attach to it by using -a
    """
    logger.info("Starting Giskard Server")
    settings = _get_settings()
    if not settings:
        version = _fetch_latest_tag()
        logger.info(f"Giskard Server not installed. Installing {version} now.")
        _write_settings({"version": version})
    else:
        version = settings["version"]

    _download_dockerfile(version.replace('v', ''))

    try:
        container = client.containers.get("giskard-server")
    except:
        container = client.containers.create(f"giskardai/giskard:{version.replace('v', '')}",
                                             detach=not attached,
                                             name="giskard-server",
                                             ports={7860: 19000, 9080: 9080})
    container.start()
    logger.info(f"Giskard Server {version} started. You can access it at http://localhost:19000")


@server.command("stop")
def stop():
    """\b
    Stop Giskard Server.

    Stops any running Giskard server. Does nothing if Giskard server is not running.
    """
    logger.info("Stopping Giskard Server")
    container = client.containers.get("giskard-server")
    container.stop()


@server.command("restart")
def restart():
    """\b
    Restart Giskard Server.

    Stops any running Giskard server and starts it again.
    """
    logger.info("Restarting Giskard Server")
    container = client.containers.get("giskard-server")
    container.stop()
    container.start()


@server.command("logs")
@click.argument("service", default="backend", type=click.Choice(["backend", "frontend", "worker"]), required=True)
def logs(service):
    """\b
    Prints logs for selected service.
    """
    logger.info(f"Logs for {service}")


@server.command("update")
@update_options
def update(version):
    """\b
    Updates Giskard Server
    """
    if version == "":
        version = _fetch_latest_tag()

    logger.info(f"Updating Giskard Server to version {version}")
    _download_dockerfile(version.replace('v', ''))

    logger.info("Giskard Server updated.")


@server.command("info")
def info():
    """\b
    Get information about the Giskard Server.
    """
    settings = _get_settings()
    if not settings:
        logger.info(f"Giskard Server is not installed. Install using $giskard server start")
        return
    else:
        version = settings["version"]

    logger.info(f"Giskard Server {version} is installed.")

    latest = _fetch_latest_tag()

    if version != latest:
        logger.info(f"A new version is available: {latest}")


def _check_downloaded(ver: str):
    try:
        client.images.get(f"giskardai/giskard:{ver}")
        logger.debug(f"Docker image for version {ver} found.")
        return True
    except docker.errors.ImageNotFound:
        return False


# Version: X.Y.Z
def _download_dockerfile(version):
    if not _check_downloaded(version):
        logger.info(f"Downloading image for version {version}")
        client.images.pull("giskardai/giskard", tag=version.replace('v', ''))


# Returns the latest tag from the GitHub API
# Format: vX.Y.Z
def _fetch_latest_tag() -> str:
    response = requests.get("https://api.github.com/repos/Giskard-AI/giskard/releases/latest")
    response.raise_for_status()
    json_response = response.json()
    tag = json_response["tag_name"]
    return tag


def _write_settings(settings):
    with open(giskard_settings_path, "w") as f:
        yaml.dump(settings, f)


def _get_settings():
    # Check the file exists first
    if not os.path.isfile(giskard_settings_path):
        return None

    # TODO: Maybe cache it ?
    return yaml.safe_load(open(giskard_settings_path, "r"))
