# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2016 Magnus (<http://www.magnus.nl>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import api, fields, models, _
import json
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = ["sale.order"]

    material_contact_person = fields.Many2one('res.partner', 'Material Contact Person', domain=[('customer','=',True)])

    # updating onchange function on field advertising_agency, customer_contact

    @api.multi
    @api.onchange('partner_id', 'advertising_agency')
    def onchange_partner_id(self):
        if self.advertising_agency:
            self.partner_id = self.advertising_agency
            self.update({
                'customer_contact': False
            })
        return super(SaleOrder, self).onchange_partner_id()


    @api.multi
    def action_submit(self):
        orders = self.filtered(lambda s: s.state in ['draft'])
        for o in orders:
            if o.order_ad4all_allow:
                if not o.material_contact_person:
                    raise UserError(
                        _('You have to fill in a material contact person.\n'
                          'Be aware, that the contact must have email and phone filled in.'))
                vals = {
                'so_customer_contacts_contact_email':
                    o.material_contact_person.email or False,
                'so_customer_contacts_contact_phone':
                    o.material_contact_person.phone or
                    o.material_contact_person.mobile or False
                }
                for key, value in vals.iteritems():
                    if value == False:
                        raise UserError(_(
                            'Field %s is required in AdPortal, but has value False'
                        ) % (key))

        return super(SaleOrder, self).action_submit()

    @api.multi
    def action_approve1(self):
        res = super(SaleOrder, self).action_approve1()
        orders = self.filtered(lambda s: s.state in ['approved1'])
        for order in orders:
            olines = []
            for line in order.order_line:
                if line.multi_line:
                    olines.append(line.id)
            if olines:
                list = self.env['sale.order.line.create.multi.lines'].create_multi_from_order_lines(orderlines=olines)
                newlines = self.env['sale.order.line'].browse(list)
                for newline in newlines:
                    if newline.deadline_check():
                        newline.page_qty_check_create()
        return res

    #Overridden not to change the state of the record while printing reports.
    @api.multi
    def print_quotation(self):
        orders = self.filtered(lambda s: s.advertising and s.state in ['draft','approved1', 'submitted', 'approved2'])
        for order in orders:
            olines = []
            for line in order.order_line:
                if line.multi_line:
                    olines.append(line.id)
            if not olines == []:
                self.env['sale.order.line.create.multi.lines'].create_multi_from_order_lines(orderlines=olines)
        self._cr.commit()
        return self.env['report'].get_action(self, 'sale.report_saleorder')

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.multi
    @api.depends('adv_issue', 'product_template_id')
    def name_get(self):
        result = []
        for sol in self:
            name = sol.adv_issue.name if sol.adv_issue else ""
            if sol.product_template_id:
                name = str(sol.id)+'-'+name+' ('+sol.product_template_id.name+')'
                result.append((sol.id, name))
        return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            domain = ['|', ('adv_issue.name', operator, name), '|', ('product_template_id.name', operator, name), '|', ('product_id.name', operator, name)]
            if name.isdigit():
                domain += [('id', '=', int(name))]
            line_ids = self.search(domain + args, limit=limit)
        else:
            line_ids = self.search(args, limit=limit)
        return line_ids.name_get()

    @api.depends('state')
    def _get_indeellijst_data(self):
        for line in self:
            prod = line.product_id
            if prod:
                line.product_width = prod.width
                line.product_height = prod.height
                line.material_id = line.recurring_id.id if line.recurring_id else line.id

    @api.model
    def default_get(self, fields_list):
        result = super(SaleOrderLine, self).default_get(fields_list)
        if 'customer_contact' in self.env.context:
            result.update({'proof_number_payer_id':self.env.context['customer_contact']})
            result.update({'proof_number_amt_payer': 1})

        result.update({'proof_number_adv_customer': False})
        result.update({'proof_number_amt_adv_customer': 0})
        return result


    @api.onchange('ad_class')
    def onchange_ad_class(self):
        vals, result = {}, {}
        if not self.advertising:
            return {'value': vals}
        titles = self.title_ids if self.title_ids else self.title or False
        domain = []
        if titles:
            product_ids = self.env['product.product']
            for title in titles:
                if title.product_attribute_value_id:
                    ids = product_ids.search([('attribute_value_ids', '=', [title.product_attribute_value_id.id])])
                    product_ids += ids
            product_tmpl_ids = product_ids.mapped('product_tmpl_id').ids
            domain = [('id', 'in', product_tmpl_ids)]
        if self.ad_class:
            vals['is_plusproposition_category'] = self.ad_class.is_plusproposition_category
            product_ids = self.env['product.template'].search(domain+[('categ_id', '=', self.ad_class.id)])
            if product_ids and len(product_ids) == 1:
                vals['product_template_id'] = product_ids[0]
            else:
                vals['product_template_id'] = False
            date_type = self.ad_class.date_type
            if date_type:
                vals['date_type'] = date_type
            else: result = {'title':_('Warning'),
                                 'message':_('The Ad Class has no Date Type. You have to define one')}
        else:
            vals['product_template_id'] = False
            vals['date_type'] = False
        return {'value': vals, 'warning': result}

    @api.onchange('circulation_type')
    def onchange_circulation_type(self):
        self.selective_circulation = self.circulation_type.selective_circulation if self.circulation_type else False

    @api.onchange('proof_number_adv_customer')
    def onchange_proof_number_adv_customer(self):
        self.proof_number_amt_adv_customer = 1 if self.proof_number_adv_customer else 0

    @api.onchange('proof_number_amt_adv_customer')
    def onchange_proof_number_amt_adv_customer(self):
        if self.proof_number_amt_adv_customer <= 0: self.proof_number_adv_customer = False

    @api.onchange('proof_number_amt_payer')
    def onchange_proof_number_amt_payer(self):
        if self.proof_number_amt_payer < 1: self.proof_number_payer_id = False

    @api.onchange('proof_number_payer_id')
    def onchange_proof_number_payer_id(self):
        self.proof_number_amt_payer = 1 if self.proof_number_payer_id else 0

    @api.depends('ad_class','title','title_ids')
    @api.multi
    def _compute_product_template_domain(self):
        """
        Compute domain for the field product_template_id.
        """
        for rec in self:
            titles = rec.title_ids if rec.title_ids else rec.title or False
            domain = []
            if titles:
                product_ids = rec.env['product.product']
                for title in titles:
                    if title.product_attribute_value_id:
                        ids = product_ids.search([('attribute_value_ids', '=', [title.product_attribute_value_id.id])])
                        product_ids += ids
                product_tmpl_ids = product_ids.mapped('product_tmpl_id').ids
                domain += [('id', 'in', product_tmpl_ids)]
            if rec.ad_class:
                domain += [('categ_id', '=', rec.ad_class.id)]
            rec.product_template_domain = json.dumps(domain)

    proof_number_payer_id = fields.Many2one('res.partner', 'Proof Number Payer ID')
    proof_number_adv_customer = fields.Many2many('res.partner', 'partner_line_proof_rel', 'line_id', 'partner_id', string='Proof Number Advertising Customer')
    proof_number_amt_payer = fields.Integer('Proof Number Amount Payer', default=1)
    proof_number_amt_adv_customer = fields.Integer('Proof Number Amount Advertising', default=1)
    product_width = fields.Float(compute='_get_indeellijst_data', readonly=True, store=False, string="Width")
    product_height = fields.Float(compute='_get_indeellijst_data', readonly=True, store=False, string="Height")
    material_id = fields.Integer(compute='_get_indeellijst_data', readonly=True, store=False, string="Material ID")
    plus_proposition_weight = fields.Integer(string='Plusproposition Weight')
    plus_proposition_height = fields.Integer(string='Plusproposition Height')
    plus_proposition_width = fields.Integer(string='Plusproposition Width')
    is_plusproposition_category = fields.Boolean(string='Plusproposition')
    selective_circulation = fields.Boolean(string='Selective Circulation')
    circulation_description = fields.Text(string='Circulation Description')
    circulation_type = fields.Many2one('circulation.type', string='Circulation Type')
    send_with_advertising_issue = fields.Boolean(string="Send with advertising issue")
    adv_issue_parent = fields.Many2one(related='adv_issue.parent_id', string='Advertising Issue Parent', readonly=True, store=True)
    product_template_domain = fields.Char(compute="_compute_product_template_domain", string="Product Template Domain")
    ad_number = fields.Char('External Reference', size=50)
    deadline = fields.Datetime(related='adv_issue.deadline', string='Deadline')

    @api.model
    def fields_get(self, fields=None, attributes=None):
        fields = super(SaleOrderLine, self).fields_get(fields, attributes=attributes)
        fields['proof_number_payer']['selectable'] = False
        fields['proof_number_payer']['sortable'] = False
        return fields

    @api.multi
    def _prepare_invoice_line(self, qty):
        res = super(SaleOrderLine, self)._prepare_invoice_line(qty)
        res['start_date'] = self.from_date
        res['end_date'] = self.to_date
        return res


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    #Overridden and calling super with mark_so_as_sent = False.
    @api.multi
    def send_mail(self, auto_commit=False):
        return super(MailComposeMessage, self.with_context(mark_so_as_sent=False)).send_mail(auto_commit=auto_commit)
