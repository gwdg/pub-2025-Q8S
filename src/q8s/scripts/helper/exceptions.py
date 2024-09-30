import logging

logger = logging.getLogger("logger")

class Q8sFatalError(Exception):
    """Critical error, should lead to termination of the program"""
    def __init__(self, message):
        self.message = "Critical error:" + message
        super().__init__(self.message)
        logger.warning(self.message)