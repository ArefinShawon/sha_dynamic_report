import io

from odoo import fields, http
from odoo.http import content_disposition, request


class SalespersonReportController(http.Controller):
    MAX_XLSX_ROWS = 1000000

    def _parse_ids(self, value):
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return [int(x) for x in value if x]
        return [int(x) for x in str(value).split(',') if x]

    def _get_data(self, date_from=None, date_to=None, salesperson_ids=None,
                  product_ids=None, category_ids=None, customer_ids=None, sale_order_statuses=None,
                  search='', offset=0, limit=200, report_type='detail', summary_group_by='salesperson',
                  min_discount=False, max_discount=False, min_margin=False, max_margin=False,
                  include_zero_margin=False, include_negative_margin=True,
                  delivery_statuses=None, invoice_statuses=None, trend_period='month',
                  aging_bucket='delivery', aging_interval=30):
        return request.env['salesperson.report'].get_report_data(
            date_from=date_from or False,
            date_to=date_to or False,
            salesperson_ids=self._parse_ids(salesperson_ids),
            product_ids=self._parse_ids(product_ids),
            category_ids=self._parse_ids(category_ids),
            customer_ids=self._parse_ids(customer_ids),
            min_discount=min_discount, max_discount=max_discount,
            min_margin=min_margin, max_margin=max_margin,
            include_zero_margin=include_zero_margin, include_negative_margin=include_negative_margin,
            delivery_statuses=self._parse_values(delivery_statuses), invoice_statuses=self._parse_values(invoice_statuses),
            sale_order_statuses=self._parse_values(sale_order_statuses),
            search=search or '',
            offset=offset, limit=limit,
            report_type=report_type, summary_group_by=summary_group_by,
            trend_period=trend_period, aging_bucket=aging_bucket, aging_interval=aging_interval,
        )

    def _parse_values(self, value):
        if not value:
            return []
        return [item for item in (value if isinstance(value, (list, tuple)) else str(value).split(',')) if item]

    def _filter_text(self, date_from, date_to, salesperson_ids, product_ids, category_ids, customer_ids,
                     sale_order_statuses, search):
        filters = []
        if date_from or date_to:
            filters.append('Date: %s to %s' % (date_from or 'Any', date_to or 'Any'))
        if salesperson_ids:
            filters.append('Salespersons: %s' % ', '.join(request.env['res.users'].browse(self._parse_ids(salesperson_ids)).mapped('name')))
        if product_ids:
            filters.append('Products: %s' % ', '.join(request.env['product.product'].browse(self._parse_ids(product_ids)).mapped('display_name')))
        if category_ids:
            filters.append('Categories: %s' % ', '.join(request.env['product.category'].browse(self._parse_ids(category_ids)).mapped('display_name')))
        if customer_ids:
            filters.append('Customers: %s' % ', '.join(request.env['res.partner'].browse(self._parse_ids(customer_ids)).mapped('display_name')))
        if sale_order_statuses:
            labels = dict(request.env['sale.order'].fields_get(allfields=['state'])['state']['selection'])
            filters.append('Statuses: %s' % ', '.join(labels.get(item, item) for item in self._parse_values(sale_order_statuses)))
        if search:
            filters.append('Search: %s' % search)
        return ' | '.join(filters) or 'No filters'

    def _report_title(self, report_type='detail', summary_group_by='salesperson'):
        return request.env['salesperson.report']._report_title(report_type, summary_group_by)

    @http.route('/sha_sales_dynamic_report/export_xlsx', type='http', auth='user')
    def export_xlsx(self, date_from=None, date_to=None, salesperson_ids=None,
                    product_ids=None, category_ids=None, customer_ids=None, sale_order_statuses=None, search='', report_type='detail', summary_group_by='salesperson',
                    min_discount=False, max_discount=False, min_margin=False, max_margin=False,
                    include_zero_margin=False, include_negative_margin=True, delivery_statuses=None, invoice_statuses=None,
                    trend_period='month', aging_bucket='delivery', aging_interval=30):
        import xlsxwriter

        filter_text = self._filter_text(date_from, date_to, salesperson_ids, product_ids, category_ids, customer_ids, sale_order_statuses, search)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 12})
        meta_fmt = workbook.add_format({'font_color': '#555555', 'text_wrap': True})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#F3F4F6', 'border': 1})
        group_fmt = workbook.add_format({'bold': True, 'bg_color': '#EAF2FF'})

        sheet = workbook.add_worksheet('Sales Report')
        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 1, 16)
        sheet.set_column(2, 2, 24)
        sheet.set_column(3, 3, 18)
        sheet.set_column(4, 4, 14)
        sheet.set_column(5, 5, 28)
        sheet.set_column(6, 8, 14)
        sheet.freeze_panes(3, 0)

        headers = (['Product Name'] if report_type == 'day_wise' else
                   ['Order', 'Date', 'Customer', 'Salesperson', 'Product', 'Quantity', 'Unit Price', 'Discount %', 'Cost', 'Revenue', 'Margin', 'Margin %'] if report_type == 'trend' else
                   ['Product'] + ['0-30', '31-60', '61-90', '91-120', '121-150', '150+'] + ['Total'] if report_type == 'aging' else
                   ['Group', 'Currency', 'Orders', 'Lines', 'Qty', 'Subtotal'] if report_type == 'summary' else
                   ['Order', 'Date', 'Customer', 'Product', 'Qty', 'Sales Price', 'Discount %', 'Cost', 'Margin', 'Margin %', 'Revenue'] if report_type == 'discount_margin' else
                   ['Order', 'Date', 'Customer', 'Product', 'Ordered Qty', 'Delivered Qty', 'Invoiced Qty', 'Remaining Qty', 'Delivery Status', 'Invoice Status'] if report_type == 'delivery_invoice' else
                   ['Order', 'Date', 'Customer', 'Salesperson', 'Company', 'Currency', 'Status', 'Product', 'Category', 'UoM', 'Qty', 'Unit Price', 'Discount %', 'Taxes', 'Subtotal'])

        sheet.merge_range(0, 0, 0, 8, self._report_title(report_type, summary_group_by), title_fmt)
        sheet.merge_range(1, 0, 1, 8, '%s | Exported: %s' % (filter_text, fields.Datetime.now()), meta_fmt)
        row = 3

        exported = 0
        offset = 0
        while exported < self.MAX_XLSX_ROWS:
            data = self._get_data(date_from, date_to, salesperson_ids, product_ids, category_ids,
                                  customer_ids, sale_order_statuses, search, offset=offset, limit=500,
                                  report_type=report_type, summary_group_by=summary_group_by,
                                  min_discount=min_discount, max_discount=max_discount,
                                  min_margin=min_margin, max_margin=max_margin,
                                  include_zero_margin=include_zero_margin, include_negative_margin=include_negative_margin,
                                  delivery_statuses=delivery_statuses, invoice_statuses=invoice_statuses,
                                  trend_period=trend_period, aging_bucket=aging_bucket, aging_interval=aging_interval)
            if not data['groups']:
                break
            for group in data['groups']:
                title = '%s (%s)' % (group['salesperson'], group['currency_symbol']) if report_type not in ('trend', 'aging', 'aging_sales', 'aging_delivery', 'aging_invoice', 'day_wise') else group['salesperson']
                sheet.write(row, 0, title, group_fmt)
                row += 1
                if report_type == 'day_wise':
                    day_headers = ['Product Name'] + group.get('day_columns', []) + ['Total']
                    for col, header in enumerate(day_headers):
                        sheet.write(row, col, header, header_fmt)
                    row += 1
                    for row_item in group.get('day_rows', []):
                        values = [row_item['product']] + [row_item['values'][idx] for idx in range(len(group.get('day_columns', [])))] + [row_item['total']]
                        for col, value in enumerate(values):
                            sheet.write(row, col, value)
                        row += 1
                    total_row = ['Total'] + group.get('day_totals', []) + [group.get('day_grand_total', 0.0)]
                    for col, value in enumerate(total_row):
                        sheet.write(row, col, value, group_fmt if col == 0 else header_fmt)
                    row += 2
                    continue
                for col, header in enumerate(headers):
                    sheet.write(row, col, header, header_fmt)
                row += 1
                if report_type == 'trend':
                    for item in group.get('trend_rows', []):
                        values = [item['order_name'], item['date_order'], item['customer'], item['salesperson'], item['product'], item['qty'], item['unit_price'], item['discount'], item['cost'], item['revenue'], item['margin'], item['margin_pct']]
                        for col, value in enumerate(values):
                            sheet.write(row, col, value)
                        row += 1
                    row += 1
                    continue
                if report_type == 'aging':
                    for metric in group.get('aging_rows', []):
                        sheet.write_row(row, 0, [metric['product']] + metric['values'] + [metric['total']])
                        row += 1
                    row += 1
                    continue
                if report_type == 'summary':
                    sheet.write_row(row, 0, [group['salesperson'], group['currency_symbol'], group['order_count'], group['line_count'], group['qty_total'], group['subtotal_total']])
                    row += 2
                    continue
                position = group['currency_position']
                number_format = '%s#,##0.00' % group['currency_symbol'] if position == 'before' else '#,##0.00%s' % group['currency_symbol']
                money_fmt = workbook.add_format({'num_format': number_format})
                for item in group['rows']:
                    if exported >= self.MAX_XLSX_ROWS:
                        break
                    if report_type == 'discount_margin':
                        values = [item['order_name'], item['date_order'], item['customer'], item['product'], item['qty'], item['unit_price'], item['discount'], item['cost'], item['subtotal'] - item['cost'], ((item['subtotal'] - item['cost']) / item['cost'] * 100) if item['cost'] else 'N/A', item['subtotal']]
                        money_columns = (5, 7, 8, 10)
                    elif report_type == 'delivery_invoice':
                        values = [item['order_name'], item['date_order'], item['customer'], item['product'], item['qty'], item['delivered_qty'], item['invoiced_qty'], item['remaining_qty'], item['delivery_status'], item['invoice_status']]
                        money_columns = ()
                    else:
                        values = [item['order_name'], item['date_order'], item['customer'], item['salesperson'], item['company'], item['currency'], item['state'], item['product'], item['category'], item['uom'], item['qty'], item['unit_price'], item['discount'], item['taxes'], item['subtotal']]
                        money_columns = (11, 14)
                    for col, value in enumerate(values):
                        sheet.write(row, col, value, money_fmt if col in money_columns else None)
                    row += 1; exported += 1
                row += 1
            offset += 500
            if not data['has_more']:
                break

        workbook.close()
        output.seek(0)
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition('sales_dynamic_report.xlsx')),
            ],
        )

    @http.route('/sha_sales_dynamic_report/export_pdf', type='http', auth='user')
    def export_pdf(self, date_from=None, date_to=None, salesperson_ids=None,
                   product_ids=None, category_ids=None, customer_ids=None, sale_order_statuses=None, search='', report_type='detail', summary_group_by='salesperson',
                   min_discount=False, max_discount=False, min_margin=False, max_margin=False,
                   include_zero_margin=False, include_negative_margin=True, delivery_statuses=None, invoice_statuses=None,
                   trend_period='month', aging_bucket='delivery', aging_interval=30):
        data = self._get_data(date_from, date_to, salesperson_ids, product_ids, category_ids,
                              customer_ids, sale_order_statuses, search, limit=500,
                              report_type=report_type, summary_group_by=summary_group_by,
                              min_discount=min_discount, max_discount=max_discount,
                              min_margin=min_margin, max_margin=max_margin,
                              include_zero_margin=include_zero_margin, include_negative_margin=include_negative_margin,
                              delivery_statuses=delivery_statuses, invoice_statuses=invoice_statuses,
                              trend_period=trend_period, aging_bucket=aging_bucket, aging_interval=aging_interval)

        filter_text = self._filter_text(date_from, date_to, salesperson_ids, product_ids, category_ids, customer_ids, sale_order_statuses, search)

        body = request.env['ir.qweb']._render(
            'sha_sales_dynamic_report.salesperson_report_pdf',
            {
                'groups': data['groups'],
                'filters': filter_text,
                'exported_at': fields.Datetime.now(),
                'report_type': report_type,
                'report_title': self._report_title(report_type, summary_group_by),
            },
        )

        # Keep horizontal breathing room, but use the full printable height.
        # Explicitly disable wkhtmltopdf header/footer spacing as those create
        # a blank band at the top and bottom of every page.
        pdf = request.env['ir.actions.report']._run_wkhtmltopdf([body], landscape=True,
            specific_paperformat_args={
                # Odoo's report API consumes these data-report-* keys. A tiny
                # positive value is used instead of 0 for compatibility with
                # Odoo 19 builds that treat zero as an unset override.
                'data-report-margin-top': 10,
                'data-report-margin-bottom': 10,
                'data-report-header-spacing': 0.01,
                'data-report-footer-spacing': 0.01,
            })

        return request.make_response(
            pdf,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Length', len(pdf)),
                ('Content-Disposition', content_disposition('sales_dynamic_report.pdf')),
            ],
        )
