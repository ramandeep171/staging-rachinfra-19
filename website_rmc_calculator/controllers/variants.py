from odoo import http
from odoo.http import request
import json


class RMCVariantsController(http.Controller):
    @http.route(
        '/rmc_calculator/variants',
        type='json',
        auth='public',
        csrf=False,
        methods=['POST'],
        website=True,
    )
    def variants_for_template(self, template_id=None, limit=20, **kw):
        if not template_id:
            domain = [
                ('website_published', '=', True),
                ('sale_ok', '=', True),
                '|', ('website_id', '=', False), ('website_id', '=', request.website.id)
            ]
            category_domain = domain + [('categ_id.complete_name', 'ilike', 'rmc')]
            templates = request.env['product.template'].sudo().search(category_domain, limit=int(limit or 20), order='website_sequence desc, id desc')
            if not templates:
                templates = request.env['product.template'].sudo().search(domain, limit=int(limit or 20), order='website_sequence desc, id desc')
            data = []
            for tmpl in templates:
                data.append({
                    'id': tmpl.id,
                    'name': tmpl.name,
                    'brand': getattr(tmpl, 'x_brand', False),
                    'grade_type': getattr(tmpl, 'x_grade_type', False),
                })
            return {'success': True, 'templates': data, 'variants': []}
        try:
            tmpl = request.env['product.template'].sudo().browse(int(template_id))
        except Exception:
            return {'success': False, 'error': 'invalid_template_id'}
        if not tmpl.exists():
            return {'success': False, 'error': 'template_not_found'}
        variants = request.env['product.product'].sudo().search([('product_tmpl_id', '=', tmpl.id)])
        data = []
        for v in variants:
            # prefer stored values
            brand = getattr(v, 'x_brand', None) or None
            grade = getattr(v, 'x_grade_type', None) or None
            # fallback: read variant attribute values (selected values)
            if not brand or not grade:
                bvals = []
                gvals = []
                for val in v.attribute_value_ids:
                    try:
                        aname = (val.attribute_id.name or '').lower()
                    except Exception:
                        aname = ''
                    if 'brand' in aname:
                        bvals.append(val.name)
                    if 'grade' in aname:
                        gvals.append(val.name)
                if not brand and bvals:
                    brand = ', '.join(bvals)
                if not grade and gvals:
                    grade = ', '.join(gvals)
            # final fallback: read template attribute_line_ids (possible values)
            if not brand or not grade:
                for line in v.product_tmpl_id.attribute_line_ids:
                    try:
                        aname = (line.attribute_id.name or '').lower()
                    except Exception:
                        aname = ''
                    vals = [x.name for x in line.value_ids]
                    if not brand and 'brand' in aname and vals:
                        brand = ', '.join(vals)
                    if not grade and 'grade' in aname and vals:
                        grade = ', '.join(vals)
            data.append({
                'id': v.id,
                'name': v.display_name,
                'brand': brand,
                'grade_type': grade,
                'list_price': float(getattr(v, 'lst_price', 0.0) or 0.0),
            })
        return {'success': True, 'variants': data}

    @http.route(
        '/rmc_calculator/variants_http',
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
        website=True,
    )
    def variants_for_template_http(self, **kw):
        # Accept template_id as GET param or POST form field for quick testing
        template_id = kw.get('template_id') or request.params.get('template_id')
        if not template_id:
            limit = int(kw.get('limit') or 20)
            domain = [
                ('website_published', '=', True),
                ('sale_ok', '=', True),
                '|', ('website_id', '=', False), ('website_id', '=', request.website.id)
            ]
            category_domain = domain + [('categ_id.complete_name', 'ilike', 'rmc')]
            templates = request.env['product.template'].sudo().search(category_domain, limit=limit, order='website_sequence desc, id desc')
            if not templates:
                templates = request.env['product.template'].sudo().search(domain, limit=limit, order='website_sequence desc, id desc')
            payload = {
                'success': True,
                'templates': [{
                    'id': tmpl.id,
                    'name': tmpl.name,
                    'brand': getattr(tmpl, 'x_brand', False),
                    'grade_type': getattr(tmpl, 'x_grade_type', False),
                } for tmpl in templates],
                'variants': [],
            }
            return request.make_response(json.dumps(payload), headers=[('Content-Type', 'application/json')])
        try:
            tmpl = request.env['product.template'].sudo().browse(int(template_id))
        except Exception:
            res = {'success': False, 'error': 'invalid_template_id'}
            return request.make_response(json.dumps(res), headers=[('Content-Type', 'application/json')])
        if not tmpl.exists():
            res = {'success': False, 'error': 'template_not_found'}
            return request.make_response(json.dumps(res), headers=[('Content-Type', 'application/json')])
        variants = request.env['product.product'].sudo().search([('product_tmpl_id', '=', tmpl.id)])
        data = []
        for v in variants:
            brand = getattr(v, 'x_brand', None) or None
            grade = getattr(v, 'x_grade_type', None) or None
            # Robust attribute value lookup
            if not brand or not grade:
                bvals = []
                gvals = []
                attr_values = None
                for fname in ('attribute_value_ids', 'product_template_attribute_value_ids', 'product_template_variant_value_ids', 'product_template_value_ids'):
                    if hasattr(v, fname):
                        try:
                            attr_values = getattr(v, fname) or None
                        except Exception:
                            attr_values = None
                        if attr_values is not None:
                            break
                if attr_values:
                    for val in attr_values:
                        try:
                            aname = (val.attribute_id.name or '').lower()
                        except Exception:
                            aname = ''
                        if 'brand' in aname:
                            bvals.append(val.name)
                        if 'grade' in aname:
                            gvals.append(val.name)
                if not brand and bvals:
                    brand = ', '.join(bvals)
                if not grade and gvals:
                    grade = ', '.join(gvals)
            if not brand or not grade:
                for line in v.product_tmpl_id.attribute_line_ids:
                    try:
                        aname = (line.attribute_id.name or '').lower()
                    except Exception:
                        aname = ''
                    vals = [x.name for x in line.value_ids]
                    if not brand and 'brand' in aname and vals:
                        brand = ', '.join(vals)
                    if not grade and 'grade' in aname and vals:
                        grade = ', '.join(vals)
            data.append({
                'id': v.id,
                'name': v.display_name,
                'brand': brand,
                'grade_type': grade,
                'list_price': float(getattr(v, 'lst_price', 0.0) or 0.0),
            })
        return request.make_response(json.dumps({'success': True, 'variants': data}), headers=[('Content-Type', 'application/json')])
