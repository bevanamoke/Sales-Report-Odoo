# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import io
import base64
import xlsxwriter
from datetime import datetime
import json
import logging

_logger = logging.getLogger(__name__)

class SalesLinesReportWizard(models.TransientModel):
    _name = 'sales.lines.report.wizard'
    _description = 'Sales Lines Report Wizard'

    # --- Filter Fields ---
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
    product_category_id = fields.Many2one(
        'product.category',
        string='Product Category'
    )
    store_expense_category_id = fields.Many2one(
        'store.expense.category',
        string='Expense Category'
    )
    date_from = fields.Date(string='From Date', required=True)
    date_to = fields.Date(string='To Date', required=True)
    
    # --- New Field for JS Widget Preview ---
    report_data_json = fields.Char(string='Report Matrix Data', readonly=True)

    @api.model
    def default_get(self, field_list):
        """Set default values"""
        res = super(SalesLinesReportWizard, self).default_get(field_list)
        today = fields.Date.context_today(self)
        res['date_from'] = today.replace(day=1)  # Default to start of month
        res['date_to'] = today
        return res

    # -------------------------------------------------------------------------
    # Report Data Calculation (Core Logic - SALES ORDERS TO STORE EXPENSE CATEGORIES)
    # -------------------------------------------------------------------------

    def _get_matrix_report_data(self):
        """
        MAP SALES ORDERS TO STORE EXPENSE CATEGORIES AND COMPUTE AMOUNTS
        """
        self.ensure_one()
        
        return self._get_sales_orders_by_expense_categories()

    def _get_sales_orders_by_expense_categories(self):
        """
        Query sales orders and map them to store expense categories
        This is where you define the mapping logic
        """
        # Build domain for sales orders
        domain = [
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['sale', 'done']),  # Only confirmed sales orders
        ]
        
        # Add customer filter if selected
        if self.customer_ids:
            domain.append(('partner_id', 'in', self.customer_ids.ids))
        
        _logger.info("=== QUERYING SALES ORDERS FOR EXPENSE CATEGORY MAPPING ===")
        _logger.info(f"Domain: {domain}")
        
        # Query sales orders
        sales_orders = self.env['sale.order'].search(domain)
        _logger.info(f"Found {len(sales_orders)} sales orders")
        
        # Filter order lines by product category if selected
        filtered_order_lines = []
        for order in sales_orders:
            for order_line in order.order_line:
                # Apply product category filter if selected
                if self.product_category_id:
                    if order_line.product_id.categ_id and order_line.product_id.categ_id.id == self.product_category_id.id:
                        filtered_order_lines.append((order, order_line))
                else:
                    filtered_order_lines.append((order, order_line))
        
        # Group data by customer (or use customers from filter)
        grouped_data = {}
        
        # If specific customers are selected, only show those customers
        if self.customer_ids:
            for customer in self.customer_ids:
                customer_name = customer.name
                # Get order lines for this customer
                customer_lines = [(order, line) for order, line in filtered_order_lines if order.partner_id.id == customer.id]
                grouped_data[customer_name] = self._get_customer_sales_lines_from_filtered(customer_lines, customer_name)
        else:
            # Group by customer from filtered order lines
            for order, order_line in filtered_order_lines:
                customer_name = order.partner_id.name
                if customer_name not in grouped_data:
                    grouped_data[customer_name] = []
                
                # Get all order lines for this customer from filtered data
                customer_lines = [(o, ol) for o, ol in filtered_order_lines if o.partner_id.name == customer_name]
                grouped_data[customer_name] = self._get_customer_sales_lines_from_filtered(customer_lines, customer_name)
        
        # If no data found, create empty structure with selected customers/category
        if not grouped_data:
            if self.customer_ids:
                for customer in self.customer_ids:
                    customer_name = customer.name
                    grouped_data[customer_name] = []
            else:
                # Show default customer sections
                default_customers = ['844 CANTEEN', '844 Kitchen', 'OPERATIONS']
                for customer_name in default_customers:
                    grouped_data[customer_name] = []
            
            # Add empty entry if category is selected
            if (self.store_expense_category_id or self.product_category_id) and grouped_data:
                for customer_name in grouped_data.keys():
                    category_info = []
                    if self.product_category_id:
                        category_info.append(f"Product Category: {self.product_category_id.name}")
                    if self.store_expense_category_id:
                        category_info.append(f"Expense Category: {self.store_expense_category_id.name}")
                    
                    description = 'No sales orders found for selected criteria'
                    if category_info:
                        description += f" ({', '.join(category_info)})"
                    
                    grouped_data[customer_name].append({
                        'order_reference': 'N/A',
                        'date': 'N/A',
                        'customer_name': customer_name,
                        'product_category': self.product_category_id.name if self.product_category_id else 'All',
                        'expense_category': self.store_expense_category_id.name if self.store_expense_category_id else 'All',
                        'description': description,
                        'product': 'N/A',
                        'quantity': 0,
                        'uom': 'PCS',
                        'price': 0.0,
                        'total': 0.0,
                    })
        
        result = {
            'grouped_data': grouped_data,
            'columns': [
                'order_reference',
                'date', 
                'customer_name',
                'product_category',
                'expense_category',
                'description',
                'product',
                'quantity',
                'uom',
                'price',
                'total'
            ],
            'date_from': self.date_from.isoformat() if self.date_from else False,
            'date_to': self.date_to.isoformat() if self.date_to else False,
            'model_context': 'sales_orders',
            'has_data': len(filtered_order_lines) > 0,
            'report_type': 'detailed_lines'
        }
        
        _logger.info(f"Generated sales orders report with {len(grouped_data)} customer groups and {len(filtered_order_lines)} order lines")
        return result

    def _get_customer_sales_lines_from_filtered(self, filtered_order_lines, customer_name):
        """
        Extract line data from filtered order lines for a specific customer
        and map to store expense categories
        """
        lines = []
        
        for order, order_line in filtered_order_lines:
            # MAP PRODUCTS/CATEGORIES TO STORE EXPENSE CATEGORIES
            expense_category = self._map_to_expense_category(order_line)
            
            line_data = {
                'order_reference': order.name,
                'date': order.date_order.strftime('%Y-%m-%d') if order.date_order else 'N/A',
                'customer_name': customer_name,
                'product_category': order_line.product_id.categ_id.name if order_line.product_id.categ_id else 'All',
                'expense_category': expense_category,
                'description': order_line.name or 'N/A',
                'product': order_line.product_id.name if order_line.product_id else 'N/A',
                'quantity': order_line.product_uom_qty,
                'uom': order_line.product_uom.name if order_line.product_uom else 'Units',
                'price': order_line.price_unit,
                'total': order_line.price_subtotal,  # Or price_total if you want tax included
            }
            lines.append(line_data)
        
        # Filter by store expense category if selected
        if self.store_expense_category_id:
            category_name = self.store_expense_category_id.name
            lines = [line for line in lines if line['expense_category'] == category_name]
        
        return lines

    def _get_customer_sales_lines(self, sales_orders, customer_name):
        """
        Extract line data from sales orders for a specific customer
        and map to store expense categories
        """
        lines = []
        
        for order in sales_orders:
            for order_line in order.order_line:
                # Apply product category filter if selected
                if self.product_category_id:
                    if not order_line.product_id.categ_id or order_line.product_id.categ_id.id != self.product_category_id.id:
                        continue
                
                # MAP PRODUCTS/CATEGORIES TO STORE EXPENSE CATEGORIES
                expense_category = self._map_to_expense_category(order_line)
                
                line_data = {
                    'order_reference': order.name,
                    'date': order.date_order.strftime('%Y-%m-%d') if order.date_order else 'N/A',
                    'customer_name': customer_name,
                    'product_category': order_line.product_id.categ_id.name if order_line.product_id.categ_id else 'All',
                    'expense_category': expense_category,
                    'description': order_line.name or 'N/A',
                    'product': order_line.product_id.name if order_line.product_id else 'N/A',
                    'quantity': order_line.product_uom_qty,
                    'uom': order_line.product_uom.name if order_line.product_uom else 'Units',
                    'price': order_line.price_unit,
                    'total': order_line.price_subtotal,  # Or price_total if you want tax included
                }
                lines.append(line_data)
        
        # Filter by store expense category if selected
        if self.store_expense_category_id:
            category_name = self.store_expense_category_id.name
            lines = [line for line in lines if line['expense_category'] == category_name]
        
        return lines

    def _map_to_expense_category(self, order_line):
        """
        MAP PRODUCTS/PRODUCT CATEGORIES TO STORE EXPENSE CATEGORIES
        Get data from actual store.expense.category model records
        """
        product = order_line.product_id
        
        # Option 1: Check if product has a direct expense category mapping
        if product and hasattr(product, 'expense_category_id') and product.expense_category_id:
            return product.expense_category_id.name
        
        # Option 2: Check if product category has an expense category mapping
        product_category = product.categ_id if product else False
        if product_category and hasattr(product_category, 'expense_category_id') and product_category.expense_category_id:
            return product_category.expense_category_id.name
        
        # Option 3: Use intelligent mapping based on existing store.expense.category records
        return self._get_expense_category_by_intelligent_mapping(product, product_category)

    def _get_expense_category_by_intelligent_mapping(self, product, product_category):
        """
        Map products to expense categories based on existing store.expense.category records
        and intelligent name matching
        """
        # Get all store.expense.category records
        expense_categories = self.env['store.expense.category'].search([])
        
        if not expense_categories:
            return 'General Expenses'
        
        # Create mapping keywords based on expense category names
        category_keywords = {}
        for category in expense_categories:
            category_name_lower = category.name.lower()
            keywords = self._extract_keywords_from_category(category_name_lower)
            category_keywords[category.name] = keywords
        
        # Try to match product category name
        if product_category and product_category.name:
            product_category_lower = product_category.name.lower()
            for category_name, keywords in category_keywords.items():
                for keyword in keywords:
                    if keyword in product_category_lower:
                        return category_name
        
        # Try to match product name
        if product and product.name:
            product_name_lower = product.name.lower()
            for category_name, keywords in category_keywords.items():
                for keyword in keywords:
                    if keyword in product_name_lower:
                        return category_name
        
        # Default to the first expense category or a general one
        default_category = expense_categories[0].name if expense_categories else 'General Expenses'
        
        # Look for a "General" or "Other" category specifically
        for category in expense_categories:
            if 'general' in category.name.lower() or 'other' in category.name.lower():
                return category.name
        
        return default_category

    def _extract_keywords_from_category(self, category_name):
        """
        Extract relevant keywords from expense category names for matching
        """
        # Common words to exclude
        exclude_words = {'expense', 'expenses', 'category', 'and', 'the', 'for', 'of', 'in', 'on', 'at', 'to'}
        
        # Split category name into words and filter out common words
        words = category_name.split()
        keywords = [word for word in words if word.lower() not in exclude_words and len(word) > 2]
        
        return keywords

    def _get_default_matrix_data(self):
        """
        Return empty structure when no specific data found
        """
        grouped_data = {}
        
        # Show default customer sections when no specific selection
        default_customers = ['844 CANTEEN', '844 Kitchen', 'OPERATIONS']
        for customer_name in default_customers:
            grouped_data[customer_name] = []
        
        _logger.info("Returning default sales orders data structure")
        return {
            'grouped_data': grouped_data,
            'columns': [
                'order_reference',
                'date', 
                'customer_name',
                'product_category',
                'expense_category',
                'description',
                'product',
                'quantity',
                'uom',
                'price',
                'total'
            ],
            'date_from': self.date_from.isoformat() if self.date_from else False,
            'date_to': self.date_to.isoformat() if self.date_to else False,
            'model_context': 'default',
            'has_data': False,
            'report_type': 'detailed_lines'
        }

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_preview(self):
        """
        Calculate report data, serialize it to JSON, and refresh the form 
        to show the matrix widget.
        """
        self.ensure_one()
        
        if self.date_from > self.date_to:
            raise UserError(_("Start date cannot be after end date."))

        _logger.info("=== GENERATING SALES ORDERS REPORT PREVIEW ===")
        _logger.info(f"Date Range: {self.date_from} to {self.date_to}")
        _logger.info(f"Customers: {[c.name for c in self.customer_ids] if self.customer_ids else 'All'}")
        _logger.info(f"Product Category: {self.product_category_id.name if self.product_category_id else 'All'}")
        _logger.info(f"Store Expense Category: {self.store_expense_category_id.name if self.store_expense_category_id else 'None'}")

        # 1. Calculate the data structure from SALES ORDERS
        report_data_dict = self._get_matrix_report_data()
        
        # 2. Serialize the data and update the transient record
        self.report_data_json = json.dumps(report_data_dict)

        _logger.info("Sales orders preview data generated successfully")
        
        # 3. Return the action to refresh/reopen the current wizard form
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Lines Report Preview'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self._context,
        }

    def print_pdf_report(self):
        """Generate PDF report (Placeholder)"""
        self.ensure_one()
        
        if self.date_from > self.date_to:
            raise UserError(_("Start date cannot be after end date."))

        report_data = self._get_matrix_report_data()
        
        # You'll need to create a PDF template for this
        raise UserError(_("PDF report functionality not yet implemented"))

    def print_xls_report(self):
        """Generate Excel report (Placeholder)"""
        self.ensure_one()
        
        if self.date_from > self.date_to:
            raise UserError(_("Start date cannot be after end date."))

        report_data = self._get_matrix_report_data()
        
        # You'll need to implement the Excel generation logic
        raise UserError(_("Excel report functionality not yet implemented"))