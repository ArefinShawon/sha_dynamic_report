from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.osv import expression


class SalespersonReport(models.AbstractModel):
    _name = 'salesperson.report'
    _description = 'Salesperson Report'

    def _display_or_na(self, value):
        return value or 'N/A'

    def _margin_percent(self, margin, cost):
        if not cost:
            return 'N/A'
        return round((margin / cost) * 100.0, 2)

    def _group_by_label(self, summary_group_by):
        return {
            'salesperson': 'Salesperson',
            'customer': 'Customer',
            'product': 'Product',
            'category': 'Product Category',
        }.get(summary_group_by, 'Salesperson')

    def _report_title(self, report_type='detail', summary_group_by='salesperson'):
        report_titles = {
            'detail': 'Sales Order Details',
            'summary': 'Sales Summary',
            'discount_margin': 'Discount and Margin',
            'delivery_invoice': 'Delivery and Invoicing Status',
            'day_wise': 'Sales Day Wise Report',
            'trend': 'Revenue, Qty and Margin Trend',
            'aging': 'Aging Report',
        }
        base = report_titles.get(report_type, 'Sales Report')
        if report_type in ('detail', 'summary'):
            return '%s by %s' % (base, self._group_by_label(summary_group_by))
        return base

    def _period_key(self, date_value, period):
        date_obj = fields.Date.to_date(date_value)
        if period == 'day':
            return date_obj.strftime('%Y-%m-%d')
        if period == 'week':
            iso_year, iso_week, _ = date_obj.isocalendar()
            return '%04d-W%02d' % (iso_year, iso_week)
        return date_obj.strftime('%Y-%m')

    def _period_label(self, period_key, period):
        if period == 'week':
            return 'Week %s' % period_key
        if period == 'day':
            return period_key
        return period_key

    def _user_timezone_boundary(self, date_value, days=0):
        local_start = datetime.combine(fields.Date.to_date(date_value), time.min) + timedelta(days=days)
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        return user_tz.localize(local_start).astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def get_filter_options(self):
        salespersons = self.env['res.users'].search_read(
            [('share', '=', False)], ['id', 'name'], order='name'
        )
        products = self.env['product.product'].search_read(
            [], ['id', 'display_name'], order='name'
        )
        categories = self.env['product.category'].search_read([], ['id', 'display_name'], order='complete_name')
        # display_name is computed in Odoo 19 and cannot be used in SQL ORDER BY.
        customers = self.env['res.partner'].search_read([('customer_rank', '>', 0)], ['id', 'display_name'], order='name')
        sale_order_statuses = self.env['sale.order'].fields_get(allfields=['state'])['state']['selection']
        return {
            'salespersons': salespersons,
            'products': products,
            'categories': categories,
            'customers': customers,
            'sale_order_statuses': sale_order_statuses,
        }

    @api.model
    def get_report_data(self, date_from=False, date_to=False, salesperson_ids=None,
                        product_ids=None, category_ids=None, customer_ids=None, sale_order_statuses=None,
                        search='', offset=0, limit=200, report_type='detail', summary_group_by='salesperson',
                        min_discount=False, max_discount=False, min_margin=False, max_margin=False,
                        include_zero_margin=False, include_negative_margin=True,
                        delivery_statuses=None, invoice_statuses=None, trend_period='month',
                        aging_bucket='delivery'):
        salesperson_ids = [int(x) for x in (salesperson_ids or []) if x]
        product_ids = [int(x) for x in (product_ids or []) if x]
        category_ids = [int(x) for x in (category_ids or []) if x]
        customer_ids = [int(x) for x in (customer_ids or []) if x]
        sale_order_statuses = sale_order_statuses or []
        limit, offset = max(1, min(int(limit or 200), 500)), max(0, int(offset or 0))
        domain = [('display_type', '=', False)]

        if date_from:
            domain.append(('order_id.date_order', '>=', fields.Datetime.to_string(self._user_timezone_boundary(date_from))))
        if date_to:
            end = self._user_timezone_boundary(date_to, days=1)
            domain.append(('order_id.date_order', '<', fields.Datetime.to_string(end)))
        if salesperson_ids:
            domain.append(('order_id.user_id', 'in', salesperson_ids))
        if product_ids:
            domain.append(('product_id', 'in', product_ids))
        if sale_order_statuses:
            domain.append(('order_id.state', 'in', sale_order_statuses))
        if category_ids:
            domain.append(('product_id.categ_id', 'child_of', category_ids))
        if customer_ids:
            domain.append(('order_id.partner_id', 'in', customer_ids))
        if min_discount is not False and min_discount != '':
            domain.append(('discount', '>=', float(min_discount)))
        if max_discount is not False and max_discount != '':
            domain.append(('discount', '<=', float(max_discount)))
        if invoice_statuses:
            domain.append(('invoice_status', 'in', invoice_statuses))
        if (search or '').strip():
            term = search.strip()
            domain = expression.AND([domain, expression.OR([[('order_id.name', 'ilike', term)], [('order_id.partner_id', 'ilike', term)], [('order_id.user_id', 'ilike', term)], [('product_id', 'ilike', term)]])])

        line_model = self.env['sale.order.line']
        total_count = line_model.search_count(domain)
        # Odoo 19 does not allow ordering a sale.order.line search by a
        # relational field property (order_id.date_order). Use the indexed
        # line id for stable, efficient pagination instead.
        lines = line_model.search(domain, order='id desc', offset=offset, limit=limit)
        if report_type in ('trend', 'day_wise', 'aging'):
            rows = {}
            for line in line_model.search(domain, order='id desc'):
                order = line.order_id
                if not order.date_order:
                    continue
                line_cost = order.currency_id._convert(
                    (line.product_id.standard_price or 0.0) * line.product_uom_qty,
                    order.currency_id, order.company_id, order.date_order.date()
                )
                line_margin = (line.price_subtotal or 0.0) - line_cost
                if report_type in ('trend', 'day_wise'):
                    period_mode = 'day' if report_type == 'day_wise' else (trend_period or 'month')
                    key = self._period_key(order.date_order.date(), period_mode)
                    label = self._period_label(key, period_mode)
                    bucket = rows.setdefault(key, {
                        'period_key': key,
                        'period_label': label,
                        'order_ids': set(),
                        'line_count': 0,
                        'qty_total': 0.0,
                        'subtotal_total': 0.0,
                        'cost_total': 0.0,
                        'margin_total': 0.0,
                        'rows': [],
                    })
                    bucket['order_ids'].add(order.id)
                    bucket['line_count'] += 1
                    bucket['qty_total'] += line.product_uom_qty or 0.0
                    bucket['subtotal_total'] += line.price_subtotal or 0.0
                    bucket['cost_total'] += line_cost
                    bucket['margin_total'] = bucket['subtotal_total'] - bucket['cost_total']
                    bucket['rows'].append({
                        'order_id': order.id,
                        'order_name': order.name,
                        'date_order': fields.Datetime.context_timestamp(self.env.user, order.date_order).strftime('%Y-%m-%d %H:%M:%S'),
                        'customer': order.partner_id.display_name,
                        'salesperson': order.user_id.name,
                        'company': order.company_id.display_name,
                        'currency': order.currency_id.name,
                        'state': order.state,
                        'product': line.product_id.display_name,
                        'category': self._display_or_na(line.product_id.categ_id.display_name),
                        'uom': line.product_uom_id.name,
                        'qty': line.product_uom_qty,
                        'unit_price': line.price_unit,
                        'discount': line.discount,
                        'taxes': ', '.join(line.tax_ids.mapped('name')),
                        'cost': line_cost,
                        'subtotal': line.price_subtotal,
                    })
                elif report_type == 'aging':
                    age_days = max((fields.Date.today() - order.date_order.date()).days, 0)
                    if age_days <= 7:
                        key = '0_7'
                        label = '0-7 Days'
                    elif age_days <= 15:
                        key = '8_15'
                        label = '8-15 Days'
                    elif age_days <= 30:
                        key = '16_30'
                        label = '16-30 Days'
                    elif age_days <= 60:
                        key = '31_60'
                        label = '31-60 Days'
                    else:
                        key = '60_plus'
                        label = '60+ Days'
                    bucket = rows.setdefault(key, {
                        'bucket_key': key,
                        'bucket_label': label,
                        'order_ids': set(),
                        'line_count': 0,
                        'qty_total': 0.0,
                        'subtotal_total': 0.0,
                        'cost_total': 0.0,
                        'margin_total': 0.0,
                        'delivered_total': 0.0,
                        'invoiced_total': 0.0,
                        'remaining_total': 0.0,
                    })
                    bucket['order_ids'].add(order.id)
                    bucket['line_count'] += 1
                    bucket['qty_total'] += line.product_uom_qty or 0.0
                    bucket['subtotal_total'] += line.price_subtotal or 0.0
                    bucket['cost_total'] += line_cost
                    bucket['margin_total'] = bucket['subtotal_total'] - bucket['cost_total']
                    bucket['delivered_total'] += line.qty_delivered or 0.0
                    bucket['invoiced_total'] += line.qty_invoiced or 0.0
                    bucket['remaining_total'] += max((line.product_uom_qty or 0.0) - (line.qty_delivered or 0.0), 0.0)

            if report_type == 'day_wise':
                period_keys = sorted(rows.keys())
                period_labels = [rows[k]['period_label'] for k in period_keys]
                product_rows = {}
                for period_key in period_keys:
                    for item in rows[period_key]['rows']:
                        product_key = '%s:%s' % (item['product'], item['product'])
                        entry = product_rows.setdefault(product_key, {
                            'product': item['product'],
                            'values': {k: 0.0 for k in period_keys},
                            'total': 0.0,
                        })
                        entry['values'][period_key] += item['qty'] or 0.0
                        entry['total'] += item['qty'] or 0.0
                day_table_rows = []
                totals = {k: 0.0 for k in period_keys}
                for entry in sorted(product_rows.values(), key=lambda x: x['product'].lower()):
                    values = [entry['values'][k] for k in period_keys]
                    for idx, k in enumerate(period_keys):
                        totals[k] += values[idx]
                    day_table_rows.append({
                        'product': entry['product'],
                        'values': values,
                        'total': entry['total'],
                    })
                groups = [{
                    'salesperson': 'Day Wise',
                    'currency_symbol': '',
                    'currency_position': 'before',
                    'group_key': 'day_wise:all',
                    'rows': [],
                    'day_columns': period_labels,
                    'day_rows': day_table_rows,
                    'day_totals': [totals[k] for k in period_keys],
                    'day_grand_total': sum(totals.values()),
                }]
            elif report_type == 'trend':
                trend_rows = []
                for period_key in sorted(rows.keys()):
                    for item in rows[period_key]['rows']:
                        revenue = item['subtotal']
                        margin = revenue - item['cost']
                        margin_pct = (margin / item['cost'] * 100.0) if item['cost'] else 'N/A'
                        trend_rows.append({
                            'order_name': item['order_name'],
                            'date_order': item['date_order'],
                            'customer': item['customer'],
                            'salesperson': item['salesperson'],
                            'product': item['product'],
                            'qty': item['qty'],
                            'unit_price': item['unit_price'],
                            'discount': item['discount'],
                            'cost': item['cost'],
                            'revenue': revenue,
                            'margin': margin,
                            'margin_pct': margin_pct,
                        })
                groups = [{
                    'salesperson': 'Trend',
                    'currency_symbol': '',
                    'currency_position': 'before',
                    'group_key': 'trend:all',
                    'rows': [],
                    'trend_rows': trend_rows,
                }]
            else:
                bucket_order = ['0_7', '8_15', '16_30', '31_60', '60_plus']
                bucket_labels = {
                    '0_7': '0-7 Days',
                    '8_15': '8-15 Days',
                    '16_30': '16-30 Days',
                    '31_60': '31-60 Days',
                    '60_plus': '60+ Days',
                }
                metrics = {
                    'Orders': 'order_count',
                    'Lines': 'line_count',
                    'Qty': 'qty_total',
                    'Delivered': 'delivered_total',
                    'Invoiced': 'invoiced_total',
                    'Remaining': 'remaining_total',
                    'Revenue': 'subtotal_total',
                    'Margin': 'margin_total',
                }
                groups = [{
                    'salesperson': 'Aging',
                    'currency_symbol': '',
                    'currency_position': 'before',
                    'group_key': 'aging:all',
                    'rows': [],
                    'aging_columns': [bucket_labels[k] for k in bucket_order],
                    'aging_rows': [{
                        'label': metric,
                        'values': [
                            (rows[k]['order_ids'] and len(rows[k]['order_ids']) or 0) if value_key == 'order_count' and k in rows else
                            rows[k]['line_count'] if value_key == 'line_count' and k in rows else
                            rows[k]['qty_total'] if value_key == 'qty_total' and k in rows else
                            rows[k]['delivered_total'] if value_key == 'delivered_total' and k in rows else
                            rows[k]['invoiced_total'] if value_key == 'invoiced_total' and k in rows else
                            rows[k]['remaining_total'] if value_key == 'remaining_total' and k in rows else
                            rows[k]['subtotal_total'] if value_key == 'subtotal_total' and k in rows else
                            rows[k]['margin_total'] if value_key == 'margin_total' and k in rows else
                            0.0
                            for k in bucket_order
                        ],
                    } for metric, value_key in metrics.items()],
                    'buckets': [{
                        'bucket_key': item['bucket_key'],
                        'bucket_label': item['bucket_label'],
                        'order_count': len(item['order_ids']),
                        'line_count': item['line_count'],
                        'qty_total': item['qty_total'],
                        'subtotal_total': item['subtotal_total'],
                        'cost_total': item['cost_total'],
                        'margin_total': item['margin_total'],
                        'delivered_total': item['delivered_total'],
                        'invoiced_total': item['invoiced_total'],
                        'remaining_total': item['remaining_total'],
                        'margin_rate': (item['margin_total'] / item['subtotal_total'] * 100) if item['subtotal_total'] else 0.0,
                    } for item in [rows[k] for k in bucket_order if k in rows]],
                }]
            return {'groups': groups, 'offset': offset, 'limit': limit, 'total_count': total_count, 'has_more': False}

        grouped = {}

        for line in lines:
            order = line.order_id
            line_cost = order.currency_id._convert(
                (line.product_id.standard_price or 0.0) * line.product_uom_qty,
                order.currency_id, order.company_id,
                order.date_order.date() if order.date_order else fields.Date.today(),
            )
            line_margin = line.price_subtotal - line_cost
            delivery_status = ('not_delivered' if (line.qty_delivered or 0.0) <= 0.0 else 'delivered' if (line.qty_delivered or 0.0) >= (line.product_uom_qty or 0.0) else 'partially_delivered')
            if report_type == 'delivery_invoice' and delivery_statuses and delivery_status not in delivery_statuses:
                continue
            if report_type == 'discount_margin':
                if min_margin not in (False, '') and line_margin < float(min_margin):
                    continue
                if max_margin not in (False, '') and line_margin > float(max_margin):
                    continue
                if not include_zero_margin and line_margin == 0:
                    continue
                if not include_negative_margin and line_margin < 0:
                    continue
            salesperson = order.user_id or self.env['res.users']
            group_records = {
                'salesperson': (salesperson.id or 0, salesperson.name or 'Unassigned'),
                'customer': (order.partner_id.id or 0, order.partner_id.display_name or 'Unknown Customer'),
                'product': (line.product_id.id, line.product_id.display_name),
                'category': (line.product_id.categ_id.id, self._display_or_na(line.product_id.categ_id.display_name)),
                'company': (order.company_id.id, order.company_id.display_name),
                'currency': (order.currency_id.id, order.currency_id.name),
            }
            if report_type in ('discount_margin', 'delivery_invoice'):
                group_id, group_name = 0, ' '
                group_prefix = report_type
            elif report_type == 'summary':
                group_id, group_name = group_records.get(summary_group_by, group_records['salesperson'])
                group_prefix = summary_group_by
            else:
                group_id, group_name = group_records.get(summary_group_by, group_records['salesperson'])
                group_prefix = summary_group_by
            salesperson_key = '%s:%s:%s' % (group_prefix, group_id, order.currency_id.id)
            if salesperson_key not in grouped:
                grouped[salesperson_key] = {
                    'salesperson_id': salesperson.id or 0,
                    'group_key': salesperson_key,
                    'currency_id': order.currency_id.id,
                    'currency_symbol': order.currency_id.symbol,
                    'currency_position': order.currency_id.position,
                    'salesperson': group_name,
                    'group_by': summary_group_by,
                    'group_label': 'Summary' if report_type == 'summary' else 'Sales Order',
                    'collapsed': False,
                    'rows': [],
                    'order_count': 0,
                    'line_count': 0,
                    'qty_total': 0.0,
                    'subtotal_total': 0.0,
                    'cost_total': 0.0,
                    'margin_total': 0.0,
                }

            grouped[salesperson_key]['rows'].append({
                    'order_id': order.id,
                    'order_name': order.name,
                    'date_order': fields.Datetime.context_timestamp(self.env.user, order.date_order).strftime('%Y-%m-%d %H:%M:%S') if order.date_order else '',
                    'customer': order.partner_id.display_name,
                    'salesperson': order.user_id.name,
                    'company': order.company_id.display_name,
                    'currency': order.currency_id.name,
                    'state': order.state,
                    'product': line.product_id.display_name,
                    'category': self._display_or_na(line.product_id.categ_id.display_name),
                    'uom': line.product_uom_id.name,
                    'qty': line.product_uom_qty,
                    'unit_price': line.price_unit,
                    'discount': line.discount,
                    'taxes': ', '.join(line.tax_ids.mapped('name')),
                    'delivered_qty': line.qty_delivered,
                    'invoiced_qty': line.qty_invoiced,
                    'remaining_qty': max(line.product_uom_qty - line.qty_delivered, 0.0),
                    'delivery_status': delivery_status,
                    'invoice_status': line.invoice_status or '',
                    'cost': line_cost,
                    'subtotal': line.price_subtotal,
                    'currency_id': order.currency_id.id,
                })
            grouped[salesperson_key]['line_count'] += 1
            grouped[salesperson_key]['qty_total'] += line.product_uom_qty or 0.0
            grouped[salesperson_key]['subtotal_total'] += line.price_subtotal or 0.0
            grouped[salesperson_key]['cost_total'] += grouped[salesperson_key]['rows'][-1]['cost'] or 0.0
            grouped[salesperson_key]['margin_total'] = grouped[salesperson_key]['subtotal_total'] - grouped[salesperson_key]['cost_total']
            grouped[salesperson_key]['order_count'] = len({r['order_id'] for r in grouped[salesperson_key]['rows']})

        return {'groups': [grouped[key] for key in sorted(grouped, key=lambda x: grouped[x]['salesperson'].lower())],
                'offset': offset, 'limit': limit, 'total_count': total_count, 'has_more': offset + limit < total_count}
