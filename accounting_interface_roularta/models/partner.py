from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Partner(models.Model):
    _inherit = "res.partner"

    def check_edit_attributes(self, vals):
        no_partner_edit = self.env.user.has_group('accounting_interface_roularta.group_no_partner_edit_check')
        attributes = ['name', 'street', 'street2', 'street_name', 'street_number', 'city',
                      'state_id', 'zip', 'country_id', 'email', 'vat', 'property_account_position_id', 'bank_ids',
                      'lang']
        for partner in self.filtered(lambda p: not p.parent_id):
            if no_partner_edit and any(attr in vals for attr in attributes):
                raise UserError(_("You can't modify partner %s"%partner.name))
        return True

    @api.multi
    def write(self, vals):
        self.check_edit_attributes(vals)
        return super(Partner, self).write(vals)

class PartnerBank(models.Model):
    _inherit = "res.partner.bank"

    @api.model
    def create(self, vals):
        no_partner_edit = self.env.user.has_group('accounting_interface_roularta.group_no_partner_edit_check')
        if no_partner_edit and 'partner_id' in vals and vals.get('partner_id'):
            partner = self.env['res.partner'].browse(vals.get('partner_id'))
            if not partner.parent_id:
                raise UserError(_("You can't modify bank account with partner %s" % partner.name))
        return super(PartnerBank, self).create(vals)

    @api.multi
    def write(self, vals):
        no_partner_edit = self.env.user.has_group('accounting_interface_roularta.group_no_partner_edit_check')
        if no_partner_edit and 'partner_id' in vals:
            partner = vals.get('partner_id')
            for acc in self:
                partner = self.env['res.partner'].browse(vals.get('partner_id')) if partner else partner
                if (acc.partner_id and not acc.partner_id.parent_id) or (partner and not partner.parent_id):
                    part = partner or acc.partner_id
                    raise UserError(_("You can't modify bank account with partner %s" % part.name))
        return super(PartnerBank, self).write(vals)


