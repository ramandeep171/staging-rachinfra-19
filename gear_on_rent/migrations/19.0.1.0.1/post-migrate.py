from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Ensure new boolean flag exists on monthly orders after upgrade."""
    if not version:
        # Fresh install paths don't need manual DDL.
        return

    cr.execute(
        """
        ALTER TABLE gear_rmc_monthly_order
        ADD COLUMN IF NOT EXISTS apply_waveoff_remaining BOOLEAN DEFAULT TRUE
        """
    )
    cr.execute(
        """
        UPDATE gear_rmc_monthly_order
        SET apply_waveoff_remaining = TRUE
        WHERE apply_waveoff_remaining IS NULL
        """
    )
