from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    x_brand = fields.Char(string='Brand', compute='_compute_attr_fields', store=True)
    x_grade_type = fields.Char(string='Grade Type', compute='_compute_attr_fields', store=True)

    @api.depends('attribute_line_ids.value_ids', 'attribute_line_ids.attribute_id')
    def _compute_attr_fields(self):
        for tmpl in self:
            brand_vals = []
            grade_vals = []
            # attribute_line_ids holds possible attribute values for template
            for line in tmpl.attribute_line_ids:
                try:
                    aname = line.attribute_id.name or ''
                except Exception:
                    aname = ''
                if aname.lower() == 'brand':
                    brand_vals = [v.name for v in line.value_ids]
                elif aname.lower() in ('grade type', 'grade_type', 'grade'):
                    grade_vals = [v.name for v in line.value_ids]
            tmpl.x_brand = ', '.join(brand_vals) if brand_vals else False
            tmpl.x_grade_type = ', '.join(grade_vals) if grade_vals else False


class ProductProduct(models.Model):
    _inherit = 'product.product'
    # compute variant attribute values per product (selected values)
    x_brand = fields.Char(string='Brand', compute='_compute_variant_attrs', store=True)
    x_grade_type = fields.Char(string='Grade Type', compute='_compute_variant_attrs', store=True)

    @api.depends('product_template_attribute_value_ids',
                 'product_template_attribute_value_ids.attribute_id',
                 'product_template_attribute_value_ids.product_attribute_value_id')
    def _compute_variant_attrs(self):
        for prod in self:
            brand_vals = []
            grade_vals = []
            try:
                for ptav in prod.product_template_attribute_value_ids:
                    try:
                        aname = ptav.attribute_id.name or ''
                    except Exception:
                        aname = ''
                    if aname.lower() == 'brand':
                        brand_vals.append(ptav.name)
                    elif aname.lower() in ('grade type', 'grade_type', 'grade'):
                        grade_vals.append(ptav.name)
            except Exception:
                pass
            prod.x_brand = ', '.join(brand_vals) if brand_vals else False
            prod.x_grade_type = ', '.join(grade_vals) if grade_vals else False
