from odoo import models, fields, api
from odoo.exceptions import UserError
import io
import base64
import xlsxwriter
import json
from datetime import datetime

class SalesStoreExpenseCategoryWizard(models.TransientModel):
    _name = 'sales.store.expense.category.wizard'
    _description = 'Sales Store Expense Category Report Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    customer_ids = fields.Many2many(
        'res.partner',
        string='Customers',
        domain=[('customer_rank', '>', 0)]
    )
    store_expense_category_ids = fields.Many2many(
        'store.expense.category',
        string='Store Expense Categories'
    )
    date_from = fields.Date(string='From Date', required=True)
    date_to = fields.Date(string='To Date', required=True)
    
    # Preview & Display Fields (NEW)
    preview_data = fields.Text(string="Preview Data")
    has_preview = fields.Boolean(string="Has Preview", default=False)
    grand_total = fields.Float(string="Grand Total", compute="_compute_preview_data_fields")
    report_data_json = fields.Char(string="Report JSON Data", compute="_compute_preview_data_fields")
    customer_info = fields.Char(string="Customer Filter", compute="_compute_customer_info")

    def _compute_customer_info(self):
        """Compute customer information for display"""
        for record in self:
            if record.customer_ids:
                customer_names = ', '.join(record.customer_ids.mapped('name'))
                record.customer_info = customer_names
            else:
                record.customer_info = "All Customers"

    @api.depends('preview_data')
    def _compute_preview_data_fields(self):
        """Computes grand_total and prepares the JSON data for the widget."""
        for record in self:
            record.grand_total = 0.0
            record.report_data_json = False
            
            if record.preview_data:
                try:
                    data = json.loads(record.preview_data)
                    record.grand_total = data.get('grand_total', 0.0)
                    record.report_data_json = record.preview_data
                except json.JSONDecodeError:
                    record.grand_total = 0.0
                    record.report_data_json = False

    @api.model
    def default_get(self, field_list):
        """Set default values"""
        res = super(SalesStoreExpenseCategoryWizard, self).default_get(field_list)
        today = fields.Date.context_today(self)
        res['date_from'] = today
        res['date_to'] = today
        return res

    def _get_report_data(self):
        """Get sale order line data grouped by store expense categories in matrix format for preview"""
        domain = [
            ('order_id.date_order', '>=', self.date_from),
            ('order_id.date_order', '<=', self.date_to),
            ('order_id.company_id', '=', self.company_id.id),
            ('order_id.state', 'in', ['sale', 'done']),  # Only confirmed sales
        ]

        # Add customer filter if selected
        if self.customer_ids:
            domain.append(('order_id.partner_id', 'in', self.customer_ids.ids))

        # Add category filter if selected
        if self.store_expense_category_ids:
            domain.append(('store_expense_id', 'in', self.store_expense_category_ids.ids))

        # Get all sale order lines in the date range
        sale_order_lines = self.env['sale.order.line'].search(domain)

        # Build matrix data for the new table structure
        matrix_data = {
            'columns': [],  # Will contain only customer columns
            'rows': [],     # Will contain store expense categories + 'Total' row
            'values': {},   # Will store amounts: key = 'row_id_column_id'
            'column_totals': {},  # Total for each column
            'row_totals': {},     # Total for each row
            'grand_total': 0.0,
            'customer_info': '',
            'category_names': []   # Store category names separately for display
        }

        # Add customer information
        if self.customer_ids:
            customer_names = ', '.join(self.customer_ids.mapped('name'))
            matrix_data['customer_info'] = customer_names
        else:
            matrix_data['customer_info'] = 'All Customers'

        # Define columns: Only Customers
        if self.customer_ids:
            for customer in self.customer_ids.sorted('name'):
                matrix_data['columns'].append({
                    'id': f'customer_{customer.id}',
                    'name': customer.name
                })
        else:
            # If no customers selected, show all customers from sale orders
            customer_ids = sale_order_lines.mapped('order_id.partner_id')
            unique_customers = []
            seen_customer_ids = set()
            for customer in customer_ids.sorted('name'):
                if customer and customer.id not in seen_customer_ids:
                    unique_customers.append(customer)
                    seen_customer_ids.add(customer.id)
            
            for customer in unique_customers:
                matrix_data['columns'].append({
                    'id': f'customer_{customer.id}',
                    'name': customer.name
                })

        # Define rows: Store Expense Categories + Total row
        category_rows = []
        if self.store_expense_category_ids:
            # Use selected categories
            for category in self.store_expense_category_ids.sorted('name'):
                category_rows.append({
                    'id': f'category_{category.id}',
                    'name': category.name
                })
                matrix_data['category_names'].append(category.name)
        else:
            # If no categories selected, show ALL categories that appear in the sale order lines
            category_ids = sale_order_lines.mapped('store_expense_id')
            unique_categories = []
            seen_category_ids = set()
            for category in category_ids.sorted('name'):
                if category and category.id not in seen_category_ids:
                    unique_categories.append(category)
                    seen_category_ids.add(category.id)
            
            # If no categories found, show all active categories
            if not unique_categories:
                all_categories = self.env['store.expense.category'].search([('active', '=', True)])
                for category in all_categories.sorted('name'):
                    category_rows.append({
                        'id': f'category_{category.id}',
                        'name': category.name
                    })
                    matrix_data['category_names'].append(category.name)
            else:
                for category in unique_categories:
                    category_rows.append({
                        'id': f'category_{category.id}',
                        'name': category.name
                    })
                    matrix_data['category_names'].append(category.name)
        
        # Add all category rows and Total row
        matrix_data['rows'] = category_rows + [{'id': 'total', 'name': 'Total'}]

        # Initialize values matrix and totals
        for row in matrix_data['rows']:
            matrix_data['row_totals'][row['id']] = 0.0
            for column in matrix_data['columns']:
                key = f"{row['id']}_{column['id']}"
                matrix_data['values'][key] = 0.0
        
        for column in matrix_data['columns']:
            matrix_data['column_totals'][column['id']] = 0.0

        # Fill the values matrix with sale order line data
        for line in sale_order_lines:
            if line.order_id.partner_id and line.store_expense_id:
                customer_id = f'customer_{line.order_id.partner_id.id}'
                category_id = f'category_{line.store_expense_id.id}'
                price_subtotal = line.price_subtotal  # Use subtotal instead of order total
                
                # Update category-customer cell
                key = f"{category_id}_{customer_id}"
                if key in matrix_data['values']:
                    matrix_data['values'][key] += price_subtotal
                
                # Update running totals
                matrix_data['row_totals'][category_id] += price_subtotal
                matrix_data['column_totals'][customer_id] += price_subtotal
                matrix_data['grand_total'] += price_subtotal

        # Now set all the calculated values in the matrix for the Total row
        for column in matrix_data['columns']:
            total_key = f"total_{column['id']}"
            matrix_data['values'][total_key] = matrix_data['column_totals'][column['id']]

        # Debug: Print totals to verify
        print("Row totals:", matrix_data['row_totals'])
        print("Column totals:", matrix_data['column_totals'])
        print("Grand total:", matrix_data['grand_total'])
        print(f"Processed {len(sale_order_lines)} sale order lines")

        return matrix_data

    def action_preview(self):
        """Show preview of the report"""
        self.ensure_one()

        # Validate dates
        if self.date_from > self.date_to:
            raise UserError("Start date cannot be after end date.")

        # Get report data (handles empty categories)
        report_data = self._get_report_data()
        
        # Store preview data as JSON and set flag to True
        self.write({
            'preview_data': json.dumps(report_data),
            'has_preview': True
        })

        return {
            'type': 'ir.actions.act_window',
            'name': f'Store Expense Category Report Preview - {self.date_from} to {self.date_to}',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {
                'customer_names': ', '.join(self.customer_ids.mapped('name')) if self.customer_ids else 'All Customers'
            }
        }

    def print_pdf_report(self):
        """Generate PDF report"""
        self.ensure_one()

        # Validate dates
        if self.date_from > self.date_to:
            raise UserError("Start date cannot be after end date.")

        matrix_data = self._get_report_data()

        # Prepare data for the template
        report_data = {
            'display_company_name': self.company_id.name,
            'date_from': self.date_from.strftime('%Y-%m-%d'),
            'date_to': self.date_to.strftime('%Y-%m-%d'),
            'datetime_now': fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'customer_names': ', '.join(self.customer_ids.mapped('name')) if self.customer_ids else False,
            'column_names': [col['name'] for col in matrix_data['columns']],
            'category_names': matrix_data['category_names'],
            'table_data': {},
            'row_totals': matrix_data['row_totals'],
            'column_totals': [matrix_data['column_totals'].get(col['id'], 0.0) for col in matrix_data['columns']],
            'grand_total': matrix_data['grand_total']
        }

        # Build table data structure
        for row in matrix_data['rows']:
            row_name = row['name']
            report_data['table_data'][row_name] = []
            
            for column in matrix_data['columns']:
                key = f"{row['id']}_{column['id']}"
                amount = matrix_data['values'].get(key, 0.0)
                report_data['table_data'][row_name].append(amount)

        return self.env.ref('sales_store_expense_report.action_store_expense_report_pdf').report_action(
            self, data=report_data
        )

    def print_xls_report(self):
        """Generate Excel report"""
        self.ensure_one()

        # Validate dates
        if self.date_from > self.date_to:
            raise UserError("Start date cannot be after end date.")

        matrix_data = self._get_report_data()

        # Create Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Store Expense Category Report')

        # Styles
        header_style = workbook.add_format({
            'bold': True, 'bg_color': '#F0F0F0', 'border': 1, 'align': 'center'
        })
        cell_style = workbook.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0.00'})
        title_style = workbook.add_format({
            'bold': True, 'font_size': 16, 'align': 'center'
        })
        total_style = workbook.add_format({
            'bold': True, 'bg_color': '#E6E6E6', 'border': 1, 'align': 'right', 'num_format': '#,##0.00'
        })
        category_style = workbook.add_format({
            'bold': True, 'border': 1, 'align': 'left', 'bg_color': '#F0F0F0'
        })

        # Title
        worksheet.merge_range(0, 0, 0, len(matrix_data['columns']),
                             'Sales Store Expense Report', title_style)

        # Company and Date info
        worksheet.write(1, 0, f"Date From: {self.date_from}")
        worksheet.write(1, 1, f"Date To: {self.date_to}")
        
        # Customer info
        customer_info = matrix_data.get('customer_info', 'All Customers')
        worksheet.write(2, 0, f"Customers: {customer_info}")

        # Headers
        row_idx = 4
        col_idx = 0
        
        # Write category header in first column
        worksheet.write(row_idx, col_idx, 'Store Expense', header_style)
        col_idx += 1
        
        # Write customer headers
        for column in matrix_data['columns']:
            worksheet.write(row_idx, col_idx, column['name'], header_style)
            col_idx += 1

        # Data rows
        row_idx = 5
        for row in matrix_data['rows']:
            col_idx = 0
            
            # Write category name in first column
            if row['id'] == 'total':
                worksheet.write(row_idx, col_idx, row['name'], total_style)
            else:
                worksheet.write(row_idx, col_idx, row['name'], category_style)
            col_idx += 1
            
            # Write amount data for each customer column
            for column in matrix_data['columns']:
                key = f"{row['id']}_{column['id']}"
                amount = matrix_data['values'].get(key, 0.0)
                
                # Apply different styles based on cell type
                if row['id'] == 'total':
                    # This is a total row cell
                    worksheet.write(row_idx, col_idx, amount, total_style)
                else:
                    # Regular amount cell
                    worksheet.write(row_idx, col_idx, amount, cell_style)
                
                col_idx += 1
            row_idx += 1

        # Adjust column widths
        worksheet.set_column(0, 0, 25)  # Store Expense column
        for i in range(1, len(matrix_data['columns']) + 1):
            worksheet.set_column(i, i, 15)  # Amount columns

        workbook.close()
        output.seek(0)

        # Create download record
        export_id = self.env['store.expense.report.download'].create({
            'excel_file': base64.b64encode(output.read()),
            'file_name': f'Store_Expense_Category_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Download Store Expense Report',
            'res_model': 'store.expense.report.download',
            'view_mode': 'form',
            'res_id': export_id.id,
            'target': 'new'
        }
    

class StoreExpenseReportDownload(models.TransientModel):
    _name = 'store.expense.report.download'
    _description = 'Store Expense Report Download'

    excel_file = fields.Binary(string='Excel File', readonly=True)
    file_name = fields.Char(string='File Name', size=256)