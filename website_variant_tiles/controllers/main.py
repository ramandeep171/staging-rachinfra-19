from math import ceil

from markupsafe import Markup

from odoo import http
from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleController


class WebsiteVariantTilesController(WebsiteSaleController):
    @http.route(
        ['/shop'],
        type='http',
        auth='public',
        website=True,
        sitemap=True,
    )
    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, tags='', **post):
        response = super().shop(
            page=page,
            category=category,
            search=search,
            min_price=min_price,
            max_price=max_price,
            tags=tags,
            **post,
        )

        request.wvt_variant_map = {}

        qcontext = getattr(response, 'qcontext', None)
        if not qcontext:
            return response

        products = qcontext.get('products')
        if not products:
            qcontext['wvt_variant_map'] = {}
            return response

        website = request.env['website'].get_current_website()
        search_templates = qcontext.get('search_product') or products
        selected_values_by_attribute = self._wvt_get_selected_values_by_attribute(qcontext)

        variant_tiles = []
        view = request.env['ir.ui.view']
        for template in search_templates:
            variants = template.product_variant_ids
            if selected_values_by_attribute:
                filtered_variants = template.env['product.product']
                for variant in variants:
                    values_by_attribute = {}
                    for ptav in variant.product_template_attribute_value_ids:
                        values_by_attribute.setdefault(ptav.attribute_id.id, set()).add(
                            ptav.product_attribute_value_id.id
                        )

                    matches_all = True
                    for attribute_id, required_values in selected_values_by_attribute.items():
                        variant_values = values_by_attribute.get(attribute_id)
                        if not variant_values or variant_values.isdisjoint(required_values):
                            matches_all = False
                            break
                    if matches_all:
                        filtered_variants += variant

                variants = filtered_variants
                if not variants:
                    continue
            if not variants:
                variants = template.product_variant_ids

            variants = variants.filtered(
                lambda variant: variant.website_published or getattr(variant, 'is_published', False)
            )
            if not variants and template.website_published:
                variants = template.product_variant_ids.filtered(lambda v: v.product_tmpl_id == template)

            for variant in variants:
                combination_info = template._get_combination_info(
                    product_id=variant.id,
                    add_qty=1.0,
                )
                price_html = view._render_template(
                    'website_sale.product_price',
                    {
                        'website': website,
                        'product': variant,
                        'combination_info': combination_info,
                        'editable': False,
                    },
                )
                variant_tiles.append({
                    'template': template,
                    'variant': variant,
                    'product_price_html': Markup(price_html),
                })

        total_variants = len(variant_tiles)
        ppg = qcontext.get('ppg') or website.shop_ppg or 21
        ppr = qcontext.get('ppr') or website.shop_ppr or 4

        if not total_variants:
            qcontext['bins'] = []
            qcontext['products'] = request.env['product.template']
            qcontext['products_prices'] = {}
            qcontext['get_product_prices'] = lambda product: {}
            qcontext['search_count'] = 0
            url_args_empty = {
                key: value
                for key, value in request.httprequest.args.items()
                if key != 'page'
            }
            qcontext['pager'] = website.pager(
                url=self._get_shop_path(qcontext.get('category')),
                total=0,
                page=1,
                step=ppg,
                scope=5,
                url_args=url_args_empty,
            )
            request.wvt_variant_map = {}
            qcontext['wvt_variant_map'] = {}
            return response

        requested_page = max(int(page or 1), 1)
        page_count = max(1, ceil(total_variants / ppg))
        if requested_page > page_count:
            requested_page = page_count

        url_args = {}
        for key in request.httprequest.args:
            values = request.httprequest.args.getlist(key)
            if not values:
                continue
            if key == 'page':
                continue
            url_args[key] = values if len(values) > 1 else values[0]
        pager = website.pager(
            url=self._get_shop_path(qcontext.get('category')),
            total=total_variants,
            page=requested_page,
            step=ppg,
            scope=5,
            url_args=url_args,
        )
        qcontext['pager'] = pager
        offset = pager['offset']

        page_tiles = variant_tiles[offset: offset + ppg]

        bins = self._wvt_build_variant_bins(page_tiles, ppr)

        qcontext['bins'] = bins
        qcontext['search_count'] = len(variant_tiles)

        template_ids_page = {tile['template'].id for tile in page_tiles}
        page_template_records = request.env['product.template'].browse(list(template_ids_page))
        qcontext['products'] = page_template_records
        products_prices = page_template_records._get_sales_prices(website)
        qcontext['products_prices'] = products_prices
        qcontext['get_product_prices'] = lambda product: products_prices.get(product.id, {})

        request.wvt_variant_map = {tile['template'].id: tile['variant'] for tile in page_tiles}
        qcontext['wvt_variant_map'] = request.wvt_variant_map
        return response

    @staticmethod
    def _wvt_build_variant_bins(tiles, ppr):
        """Group the variant tiles into rows compatible with the website grid."""
        bins = []
        current_row = []

        for tile in tiles:
            if len(current_row) >= ppr:
                bins.append(current_row)
                current_row = []

            current_row.append({
                'product': tile['template'],
                'variant': tile['variant'],
                'product_price': tile.get('product_price_html'),
                'ribbon': tile['template'].sudo().website_ribbon_id,
                'x': 1,
                'y': 1,
            })

        if current_row:
            bins.append(current_row)

        return bins

    def _wvt_get_selected_values_by_attribute(self, qcontext):
        """Return a mapping of attribute_id -> set(product.attribute.value ids) filtered in the URL."""
        selected_by_attribute = {}

        pav_model = request.env['product.attribute.value']
        ptav_model = request.env['product.template.attribute.value']

        attribute_value_dict = qcontext.get('attrib_values') or {}
        for raw_attr_id, raw_value_ids in attribute_value_dict.items():
            try:
                attr_id = int(raw_attr_id)
            except (TypeError, ValueError):
                continue

            pav_records = pav_model.browse(raw_value_ids).exists()
            if pav_records:
                selected_by_attribute.setdefault(attr_id, set()).update(pav_records.ids)
                continue

            ptav_records = ptav_model.browse(raw_value_ids).exists()
            for ptav in ptav_records:
                selected_by_attribute.setdefault(ptav.attribute_id.id, set()).add(
                    ptav.product_attribute_value_id.id
                )

        # Legacy ?attrib= parameters use template attribute values (ptav); map them back to pav.
        for raw_attrib in request.httprequest.args.getlist('attrib'):
            if not raw_attrib:
                continue
            try:
                raw_attr_id, raw_values = raw_attrib.split('-', 1)
            except ValueError:
                continue
            try:
                attr_id = int(raw_attr_id)
            except ValueError:
                continue
            for token in raw_values.split(','):
                token = token.strip()
                if not token:
                    continue
                try:
                    ptav = ptav_model.browse(int(token))
                except ValueError:
                    continue
                if not ptav.exists():
                    continue
                selected_by_attribute.setdefault(attr_id, set()).add(
                    ptav.product_attribute_value_id.id
                )

        # /shop?attribute_values=... uses product.attribute.value IDs.
        for raw_value in request.httprequest.args.getlist('attribute_values'):
            if not raw_value:
                continue
            for token in raw_value.replace('[', '').replace(']', '').split(','):
                token = token.strip()
                if not token:
                    continue
                try:
                    pav = pav_model.browse(int(token))
                except ValueError:
                    continue
                if not pav.exists():
                    continue
                selected_by_attribute.setdefault(pav.attribute_id.id, set()).add(pav.id)

        return {attr_id: values for attr_id, values in selected_by_attribute.items() if values}
