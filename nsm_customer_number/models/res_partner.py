from odoo import api, fields, models, _

class Partner(models.Model):
    _inherit = 'res.partner'

    nsm_customer_number = fields.Char('Klantnummer NSM',
        help='This is old customer "ref" code.',
        readonly= True
    )
    roularta_customer_name = fields.Char('Roularta Customer Name')

