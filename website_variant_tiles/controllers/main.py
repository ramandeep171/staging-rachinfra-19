from odoo import http
from odoo.http import request

from odoo.addons.website_sale.controllers.main import TableCompute, WebsiteSale as WebsiteSaleController


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

        search_templates = qcontext.get('search_product') or products
        selected_values_by_attribute = self._wvt_get_selected_values_by_attribute(qcontext)

        variant_tiles = []
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
                variant_tiles.append({
                    'template': template,
                    'variant': variant,
                })

        if not variant_tiles:
            qcontext['wvt_variant_map'] = {}
            return response

        website = request.env['website'].get_current_website()
        ppg = qcontext.get('ppg') or website.shop_ppg or 21
        ppr = qcontext.get('ppr') or website.shop_ppr or 4

        url_args = {}
        for key in request.httprequest.args:
            values = request.httprequest.args.getlist(key)
            if not values:
                continue
            url_args[key] = values if len(values) > 1 else values[0]
        pager = website.pager(
            url=self._get_shop_path(qcontext.get('category')),
            total=len(variant_tiles),
            page=page,
            step=ppg,
            scope=5,
            url_args=url_args,
        )
        qcontext['pager'] = pager
        offset = pager['offset']

        page_tiles = variant_tiles[offset: offset + ppg]

        table_computer = TableCompute()
        bins = table_computer.process([tile['template'] for tile in page_tiles], ppg=ppg, ppr=ppr)

        tiles_iter = iter(page_tiles)
        for row in bins:
            for cell in row:
                tile = next(tiles_iter, None)
                if not tile:
                    break
                cell['product'] = tile['template']
                cell['variant'] = tile['variant']
                cell['ribbon'] = cell['product'].sudo().website_ribbon_id

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

    def _wvt_get_selected_values_by_attribute(self, qcontext):
        """Return a mapping of attribute_id -> set(product.attribute.value ids) filtered in the URL."""
        attribute_value_dict = qcontext.get('attrib_values') or {}
        selected_by_attribute = {
            int(attr_id): set(value_ids)
            for attr_id, value_ids in attribute_value_dict.items()
        }

        # Legacy ?attrib= parameters use template attribute values (ptav); map them back to pav.
        ptav_model = request.env['product.template.attribute.value']
        for raw_attrib in request.httprequest.args.getlist('attrib'):
            if not raw_attrib:
                continue
            try:
                _, raw_values = raw_attrib.split('-', 1)
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
                selected_by_attribute.setdefault(ptav.attribute_id.id, set()).add(
                    ptav.product_attribute_value_id.id
                )

        # /shop?attribute_values=... uses product.attribute.value IDs.
        pav_model = request.env['product.attribute.value']
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
