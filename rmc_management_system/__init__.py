from . import models
from . import wizard
from . import controllers

import logging

_logger = logging.getLogger(__name__)

def post_init(env):
	"""Post-init hook for rmc_management_system.
	Keep it lightweight; reserved for future data migrations.
	"""
	_logger.info("rmc_management_system post-init: completed (no-op)")
