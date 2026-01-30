from odoo import models, fields

class StoreExpenseLocation(models.Model):
    _name = 'store.expense.location'
    _description = 'Store Expense Location'
    _order = 'name'

    name = fields.Char(string='Location Name', required=True)
    code = fields.Char(string='Code')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

class StoreExpenseCategory(models.Model):
    _name = 'store.expense.category'
    _description = 'Store Expense Category'
    _order = 'name'

    name = fields.Char(string='Category Name', required=True)
    code = fields.Char(string='Code')
    active = fields.Boolean(default=True)

class StoreExpense(models.Model):
    _name = 'store.expense'
    _description = 'Store Expense'
    _order = 'date desc'

    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    customer_id = fields.Many2one(
        'res.partner', 
        string='Customer',
        domain=[('customer_rank', '>', 0)]  # Only show customers
    )
    location_id = fields.Many2one('store.expense.location', string='Location', required=True)
    category_id = fields.Many2one('store.expense.category', string='Expense Category', required=True)
    amount = fields.Float(string='Amount', required=True)
    description = fields.Text(string='Description')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    reference = fields.Char(string='Reference')