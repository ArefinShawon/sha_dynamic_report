{
    'name': 'Sales Dynamic Report',
    'version': '19.0.1.0.1',
    'category': 'Sales/Sales',
    'summary': 'Dynamic, filterable sales report with Excel/PDF export',
    'description': """Dynamic sales reporting by salesperson, product, and order status with Excel/PDF export.""",
    'author': 'Shawon',
    'depends': ['sale_management', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/sales_report_views.xml',
        'report/sales_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sha_sales_dynamic_report/static/src/js/sales_report.js',
            'sha_sales_dynamic_report/static/src/xml/sales_report_templates.xml',
            'sha_sales_dynamic_report/static/src/scss/sales_report.scss',
        ],
    },
    'external_dependencies': {'python': ['xlsxwriter']},
    'currency': 'USD',
    'price': 50.00,
    'license': 'OPL-1',
    'installable': True,
    'application': True,
}
