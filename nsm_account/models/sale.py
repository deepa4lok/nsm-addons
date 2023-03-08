# -*- coding: utf-8 -*-

from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.multi
    @api.depends('order_id.invoicing_property_id', 'order_id.invoicing_date')
    def _calculate_cutoff_date(self):
        res = super(SaleOrderLine, self)._calculate_cutoff_date()
        for line in self:
            line_print = not(line.product_id.categ_id.digital)
            if line.invoicing_property_id.inv_whole_order_enddate:
                if line_print:
                    cutoff_date = line.issue_date
                else:
                    cutoff_date = line.to_date
                line.update({'cutoff_date': cutoff_date})
        return res
