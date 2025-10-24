# -*- coding: utf-8 -*-

from . import res_config_settings
from . import diesel_log
"""Keep only active models; equipment log model kept if still needed separately."""
try:
	from . import diesel_equipment_log  # optional legacy
except Exception:
	pass
from . import hr_attendance
from . import fleet_vehicle
from . import stock_picking