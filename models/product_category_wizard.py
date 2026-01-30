from odoo import models, fields, api
from odoo.exceptions import UserError
import io
import base64
import xlsxwriter
import json

class SalesProductCategoryWizard(models.TransientModel):
    _name = 'sales.product.category.wizard'
    _description = 'Sales Product Category Report Wizard'

    # Configuration Fields
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True)
    customer_ids = fields.Many2many('res.partner', string='Customers', domain=[('customer_rank', '>', 0)])
    product_category_ids = fields.Many2many('product.category', string='Product Categories', required=False)
    date_from = fields.Date(string='From Date', required=True)
    date_to = fields.Date(string='To Date', required=True)
    
    # Preview & Display Fields
    preview_data = fields.Text(string="Preview Data")
    has_preview = fields.Boolean(string="Has Preview", default=False)
    grand_total = fields.Float(string="Grand Total", compute="_compute_preview_data_fields")
    report_data_json = fields.Char(string="Report JSON Data", compute="_compute_preview_data_fields")

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
        res = super().default_get(field_list)
        today = fields.Date.context_today(self)
        res['date_from'] = today
        res['date_to'] = today
        return res

    def _get_report_data(self):
        """Get product category sales data and returns a JSON-serializable dict."""
        self.ensure_one()
        
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError("Start date cannot be after end date.")

        # Build domain for sale orders
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['sale', 'done']), 
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
        ]
        
        if self.customer_ids:
            domain.append(('partner_id', 'in', self.customer_ids.ids))
        
        # Fetch sale orders
        orders = self.env['sale.order'].search(domain)
        
        # Initialize matrix structure
        matrix_data = {
            'rows': [], 
            'columns': [], 
            'values': {},
            'row_totals': {},
            'column_totals': {},
            'grand_total': 0.0
        }
        
        # Use selected categories or create default structure
        if self.product_category_ids:
            categories = self.product_category_ids
            matrix_data['rows'] = [{'id': cat.id, 'name': cat.name} for cat in categories]
        else:
            # Default rows when no categories selected
            matrix_data['rows'] = [
                {'id': 1, 'name': 'All'},
                {'id': 2, 'name': 'Total'}
            ]
            categories = []  # Empty for processing logic
        
        # Determine the set of customers that will be the columns
        if self.customer_ids:
            customers = self.customer_ids
        else:
            customers = orders.mapped('partner_id').sorted(key=lambda c: c.name) 

        # Build column headers
        matrix_data['columns'] = [{'id': cust.id, 'name': cust.name} for cust in customers]
        
        # Initialize value, row, and column totals dictionaries
        for row in matrix_data['rows']:
            for customer in customers:
                key = f"{row['id']}_{customer.id}" 
                matrix_data['values'][key] = 0.0
            matrix_data['row_totals'][row['id']] = 0.0
        
        for customer in customers:
            matrix_data['column_totals'][customer.id] = 0.0
        
        # Only process orders if we have actual categories
        if categories:
            for order in orders:
                customer_id = order.partner_id.id
                if self.customer_ids and customer_id not in self.customer_ids.ids:
                    continue

                for line in order.order_line.filtered(lambda l: l.product_id.categ_id.id in categories.ids):
                    category_id = line.product_id.categ_id.id
                    amount = line.price_subtotal 
                    
                    key = f"{category_id}_{customer_id}" 
                    
                    if key in matrix_data['values']:
                        matrix_data['values'][key] += amount
                        matrix_data['row_totals'][category_id] += amount
                        matrix_data['column_totals'][customer_id] += amount
                        matrix_data['grand_total'] += amount
        
        return matrix_data

    def action_preview(self):
        """Calculates report data, stores it in preview_data, and reloads the view."""
        self.ensure_one()
        
        # REMOVED: No longer raise error when no categories selected
        # if not self.product_category_ids:
        #     raise UserError("Please select at least one product category.")

        # Get actual report data (will handle empty categories)
        report_data = self._get_report_data()
        
        # Store preview data as JSON and set flag to True
        self.write({
            'preview_data': json.dumps(report_data),
            'has_preview': True
        })
        
        # Return to same view with updated fields
        return {
            'type': 'ir.actions.act_window',
            'name': f'Product Category Report Preview - {self.date_from} to {self.date_to}',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
        

    def print_preview_pdf(self):
        """Generates the PDF report for preview."""
        self.ensure_one()
        report_data = self._get_report_data()
        
        return self.env.ref('sales_store_expense_report.report_product_category_preview').report_action(self, data={
            'report_data': report_data,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company': self.company_id.name,
        })

    def print_pdf_report(self):
        """Generates the final PDF report."""
        self.ensure_one()
        report_data = self._get_report_data()
        
        return self.env.ref('sales_store_expense_report.report_product_category_sales').report_action(self, data={
            'report_data': report_data,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company': self.company_id.name,
            'wizard_id': self.id,
        })

    def print_xls_report(self):
        """Generates the Excel report."""
        self.ensure_one()
        report_data = self._get_report_data()
        
        # Create Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Product Category Sales')
        
        # Formats
        header_format = workbook.add_format({'bold': True, 'bg_color': '#366092', 'font_color': 'white', 'border': 1})
        total_format = workbook.add_format({'bold': True, 'bg_color': '#F2F2F2', 'border': 1})
        currency_format = workbook.add_format({'num_format': '#,##0.00'})
        currency_total_format = workbook.add_format({'num_format': '#,##0.00', 'bold': True, 'bg_color': '#F2F2F2', 'border': 1})
        
        # Write title
        title_format = workbook.add_format({'bold': True, 'size': 16})
        worksheet.merge_range(0, 0, 0, 2, 'Product Category Sales Report', title_format)
        worksheet.merge_range(1, 0, 1, 2, f'Date Range: {self.date_from} to {self.date_to}')
        worksheet.merge_range(2, 0, 2, 2, f'Company: {self.company_id.name}')
        
        # Get customers from report data
        customer_ids_in_data = list(report_data['column_totals'].keys())
        customers = self.env['res.partner'].browse(customer_ids_in_data)
        
        # Write headers
        col_offset = 1
        worksheet.write(4, 0, 'Product Category', header_format)
        
        for col_idx, customer in enumerate(customers):
            worksheet.write(4, col_idx + col_offset, customer.name, header_format)
        
        total_col = len(customers) + col_offset
        worksheet.write(4, total_col, 'Total', header_format)
        
        # Write data - handle both cases (with and without categories)
        row = 5
        if self.product_category_ids:
            # Write actual categories
            for category in self.product_category_ids:
                worksheet.write(row, 0, category.name)
                col_idx = 0
                
                for customer in customers:
                    key = f"{category.id}_{customer.id}"
                    amount = report_data['values'].get(key, 0.0)
                    worksheet.write(row, col_idx + col_offset, amount, currency_format)
                    col_idx += 1
                
                row_total = report_data['row_totals'].get(category.id, 0.0)
                worksheet.write(row, total_col, row_total, currency_total_format)
                row += 1
        else:
            # Write default rows when no categories selected
            for row_data in report_data['rows']:
                worksheet.write(row, 0, row_data['name'])
                col_idx = 0
                
                for customer in customers:
                    key = f"{row_data['id']}_{customer.id}"
                    amount = report_data['values'].get(key, 0.0)
                    worksheet.write(row, col_idx + col_offset, amount, currency_format)
                    col_idx += 1
                
                row_total = report_data['row_totals'].get(row_data['id'], 0.0)
                worksheet.write(row, total_col, row_total, currency_total_format)
                row += 1
        
        # Write column totals
        worksheet.write(row, 0, 'TOTAL', total_format)
        
        col_idx = 0
        grand_total = 0.0
        
        for customer in customers:
            col_total = report_data['column_totals'].get(customer.id, 0.0)
            worksheet.write(row, col_idx + col_offset, col_total, currency_total_format)
            grand_total += col_total
            col_idx += 1
        
        worksheet.write(row, total_col, grand_total, currency_total_format)
        
        # Adjust column widths
        worksheet.set_column(0, 0, 30)
        worksheet.set_column(1, total_col, 15)
        
        workbook.close()
        output.seek(0)
        
        # Return file download
        file_data = base64.b64encode(output.getvalue())
        filename = f'product_category_sales_{self.date_from}_{self.date_to}.xlsx'
        
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': file_data,
            'type': 'binary',
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }