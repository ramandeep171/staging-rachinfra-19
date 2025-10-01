"""Controller module intentionally left minimal for Odoo 19.

Previous versions overrode a JSON controller to extend suggested recipients.
In v19 that logic is moved to a model override placed under models/.
This file remains so the module's original structure stays compatible.
"""

# No controller overrides required currently.