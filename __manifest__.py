{
    'name': 'Sales Store Expense Report',
    'version': '18.0.1.0.0',
    'category': 'Sales/Reporting',
    'summary': 'Store expense category wise sales and expense reporting',
    'description': """
        Generate detailed reports for store expense categories including sales and expenses
        with PDF and Excel export capabilities.
    """,
    'author': 'OKS',
    'website': 'https://www.oks.co.ke',
    'depends': ['sale', 'account', 'web'], # <-- CRITICAL FIX: ADDED 'web'
    'data': [
        'security/ir.model.access.csv', 
        'views/sale_order_views.xml',        
        'views/report_store_expense_wizard_pdf.xml',
        'views/product_category_report_pdf.xml',
        'views/store_expense_views.xml',               
        'wizards/store_expense_report_wizard_views.xml',
        'views/sales_lines_wizard_views.xml',
        'reports/store_expense_report_templates.xml',
        'views/product_category_wizard_views.xml'
    ],
    'assets': {
        'web.assets_backend': [
            'sales_store_expense_report/static/src/js/report_matrix_widget.js',
            'sales_store_expense_report/static/src/js/product_category_widget.js',

            'sales_store_expense_report/static/src/xml/report_matrix_template.xml',
            'sales_store_expense_report/static/src/xml/product_category_template.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}