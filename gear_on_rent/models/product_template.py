from odoo import _, api, fields, models
from odoo.fields import Command


class ProductTemplate(models.Model):
    """Flag products that should launch the RMC production flow."""

    _inherit = "product.template"

    gear_is_production = fields.Boolean(
        string="RMC Production Item",
        help="Enable to run the Gear On Rent production workflow whenever this product appears on a sale order.",
        tracking=True,
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    gear_is_production = fields.Boolean(
        related="product_tmpl_id.gear_is_production",
        store=True,
        readonly=False,
    )

    attribute_value_ids = fields.Many2many(
        comodel_name="product.attribute.value",
        string="Attribute Values",
        compute="_compute_attribute_value_ids",
        inverse="_inverse_attribute_value_ids",
        help="Compatibility alias allowing legacy XML data to keep writing attribute values on variants.",
    )

    @api.depends("product_template_attribute_value_ids")
    def _compute_attribute_value_ids(self):
        for product in self:
            product.attribute_value_ids = product.product_template_attribute_value_ids.mapped(
                "product_attribute_value_id"
            )

    def _inverse_attribute_value_ids(self):
        inactive_ctx = dict(self.env.context, active_test=False)
        ptal_ctx = dict(inactive_ctx, create_product_product=False, update_product_template_attribute_values=False)
        ProductTemplateAttributeLine = self.env["product.template.attribute.line"].with_context(ptal_ctx)
        ProductTemplateAttributeValue = self.env["product.template.attribute.value"].with_context(inactive_ctx)
        for product in self:
            values = product.attribute_value_ids
            if not values:
                product.product_template_attribute_value_ids = False
                continue

            ptav_ids = []
            for value in values:
                line = ProductTemplateAttributeLine.search(
                    [
                        ("product_tmpl_id", "=", product.product_tmpl_id.id),
                        ("attribute_id", "=", value.attribute_id.id),
                    ],
                    limit=1,
                )
                if not line:
                    line = ProductTemplateAttributeLine.create(
                        {
                            "product_tmpl_id": product.product_tmpl_id.id,
                            "attribute_id": value.attribute_id.id,
                            "value_ids": [Command.set([value.id])],
                        }
                    )
                elif value not in line.value_ids:
                    line.write({"value_ids": [Command.link(value.id)]})

                ptav = ProductTemplateAttributeValue.search(
                    [
                        ("product_tmpl_id", "=", product.product_tmpl_id.id),
                        ("attribute_id", "=", value.attribute_id.id),
                        ("product_attribute_value_id", "=", value.id),
                    ],
                    limit=1,
                )
                if ptav:
                    if not ptav.ptav_active or ptav.attribute_line_id != line:
                        ptav.with_context(active_test=False).write(
                            {"ptav_active": True, "attribute_line_id": line.id}
                        )
                else:
                    ptav = ProductTemplateAttributeValue.create(
                        {
                            "product_attribute_value_id": value.id,
                            "attribute_line_id": line.id,
                            "price_extra": value.default_extra_price,
                        }
                    )
                ptav_ids.append(ptav.id)

            product.product_template_attribute_value_ids = ProductTemplateAttributeValue.browse(ptav_ids)
