# -*- coding: utf-8 -*-

from odoo import models, fields, api

class nsm_invoicing_property(models.Model):
	_inherit = 'invoicing.property'

	inv_whole_order_enddate = fields.Boolean(string="Invoice print order lines on issue date, invoice online order lines on end date")

	selected_invoicing_property_timing = fields.Selection(selection_add=[('inv_whole_order_enddate', 'Invoice print order lines on issue date, invoice online order lines on end date'),])

	@api.multi
	def write(self, vals):
		""" Convert a radio button value to a list of booleans (zero based) """
		fields_timing = {
			'inv_whole_order_enddate':self.inv_whole_order_enddate,
		}
		if 'selected_invoicing_property_timing' in vals:
			for field_timing in fields_timing:
				if field_timing == str(vals['selected_invoicing_property_timing']):
					vals[field_timing] = True
				else:
					vals[field_timing] = False
		return super(nsm_invoicing_property, self).write(vals)
