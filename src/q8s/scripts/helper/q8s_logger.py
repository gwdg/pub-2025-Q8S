"""Offers logging utilities for the entire program.
Should be imported in every file as

    "logger = logging.getLogger("logger")"

:author: Jonathan Decker
taken from Ironik project, under MIT license: https://gitlab-ce.gwdg.de/jdecker/ironik
"""

import logging
import logging.config
import pathlib
import time


def setup_logger(
    logger_name: str = "logger",
    console_level=logging.CRITICAL,
    log_file_level=logging.INFO,
    logs_to_keep: int = 20,
    create_log_files: bool = True,
    path_to_logs: pathlib.Path = None,
) -> None:
    """:description: Sets up a logger with formatting, log file creation, settable console and log file logging levels as
     well as automatic deletion of old log files.
    :param logger_name: Name of the logger profile, standard is logger, this should not be changed except for testing
    :type logger_name: str
    :param console_level: logging level on console, standard is INFO
    :type console_level: logging level
    :param log_file_level: logging level in log file, standard is DEBUG
    :type log_file_level: logging level
    :param logs_to_keep: number of log files to keep before deleting the oldest one, standard is 20
    :type logs_to_keep: int
    :param create_log_files: Whether to create log files or only log to console
    :type create_log_files: bool
    :param path_to_logs: path to the directory for saving the logs, standard is current working directory / logs
    :type path_to_logs: pathlib.PATH
    :return: None, but the logger may now be accessed via logging.getLogger(logger_name), standard is logger
    :rtype: None
    """

    def delete_oldest_log(path_to_logs):
        """:description: Finds and deletes the oldest .log file in the given file path
        :param path_to_logs: file path to the log folder
        :type path_to_logs: pathlib.PATH
        :return: None
        :rtype: None
        """
        # assert preconditions
        assert path_to_logs.exists()
        assert path_to_logs.is_dir()
        assert len(list(path_to_logs.glob("*.log"))) > 0

        # find oldest log
        _, file_path = min((f.stat().st_mtime, f) for f in path_to_logs.glob("*.log"))
        pathlib.Path.unlink(file_path)

    # assert preconditions
    logging_levels = [
        logging.CRITICAL,
        logging.ERROR,
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
    ]
    assert console_level in logging_levels
    assert log_file_level in logging_levels
    assert isinstance(logs_to_keep, int)
    assert isinstance(create_log_files, bool)
    assert isinstance(path_to_logs, pathlib.Path) or path_to_logs is None

    if path_to_logs is None:
        path_to_logs = pathlib.Path.cwd() / "logs"

    assert (
        len(logging.getLogger(logger_name).handlers) == 0
    ), f"Logger {logger_name} already has the handler: {logging.getLogger(logger_name).handlers} "

    # create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # if create_log_files is True, check for logs folder or make one
    fh_did_not_fail = True
    try:
        if create_log_files:
            if not ((path_to_logs.exists()) and path_to_logs.is_dir()):
                path_to_logs.mkdir()

            # check if old logs need to be deleted
            if logs_to_keep >= 0:
                while len(list((path_to_logs.glob("*.log")))) > logs_to_keep:
                    delete_oldest_log(path_to_logs)

            # create file handler
            time_str = time.strftime("%d-%m-%Y_%H-%M-%S")
            log_file_name = f"log_{time_str}.log"
            file_handler = logging.FileHandler(str(path_to_logs / log_file_name))
            file_handler.setLevel(log_file_level)
    except PermissionError:
        fh_did_not_fail = False

    # create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)

    # create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)-8s - %(message)s")
    if create_log_files and fh_did_not_fail:
        file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # add handlers to logger
    if create_log_files and fh_did_not_fail:
        logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.debug(f"Finished setting up {logger_name}: logger")

    if not fh_did_not_fail:
        logger.warning("Logger File handler failed due to missing permissions, no log file will be created")
