from odoo import models, fields, api

# 1. Existing Sale Order Line Model Extension
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    
    store_expense_id = fields.Many2one(
        'store.expense.category',  # Adjust to your actual model name
        string='Store Expense Category',
        help='Store expense category for this order line'
    )

# 2. New Sale Order Model Extension to make date_order editable
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Define the states where the Order Date should be editable (not read-only)
    # We explicitly include 'sale' (Confirmed) and 'done' (Locked) states.
    EDITABLE_DATE_STATES = {
        'draft': [('readonly', False)],
        'sent': [('readonly', False)],
        'sale': [('readonly', False)],  # <<-- Editable when Confirmed
        'done': [('readonly', False)],  # <<-- Editable when Locked
    }

    # Override the existing date_order field with the new states
    date_order = fields.Datetime(
        # The key change is applying the 'states' dictionary to the inherited field
        states=EDITABLE_DATE_STATES,
        
        # OPTIONAL: You can restrict this ability to only certain user groups 
        # For example, only allowing 'Sales Manager' to edit historical dates:
        # groups='sales_team.group_salemanager',
    )