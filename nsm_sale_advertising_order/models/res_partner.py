# -*- coding: utf-8 -*-
# Copyright 2017 Willem hulshof - <w.hulshof@magnus.nl>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = "res.partner"

    def name_get(self):
        """ Add ref to name"""
        if not 'update_partner_ref' in self.env.context:
            return super(ResPartner, self).name_get()
        res = []
        for partner in self:
            if partner.ref:
                name = '[%s] %s' % (partner.ref, partner.name)
            else:
                name = '%s' % (partner.name)
            res.append((partner.id, name))
        return res

    def name_get_custom_ref(self, partner_ids):
        if not partner_ids:
            return []
        res = []
        domain = False
        if 'searchFor' in self.env.context:
            domain = self.env.context['searchFor']
        for record in partner_ids:
            str_name = record.name
            if domain:
                if record.zip and domain == 'zip':
                    name = '['+record.ref+']'+str_name+'['+record.zip+']'
                    res.append((record.id, name))
                elif record.ref and domain == 'ref':
                    name = '['+record.ref+']'+str_name+'['+record.zip+']'
                    res.append((record.id, name))
                else:
                    res.append((record.id, str_name))
            else:
                res.append((record.id, str_name))
        return res

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if not args:
            args = []
        args = args[:]
        ctx = self.env.context.copy()
        ctx.update({'searchFor': 'name'}) #default search for name
        if name:
            partner_ids = self.search([('zip', '=like', name + "%")] + args, limit=limit)
            ctx.update({'searchFor': 'zip'}) if partner_ids else ctx
            if not partner_ids:
                partner_ids = self.search([('ref', '=like', name + "%")] + args, limit=limit)
                ctx.update({'searchFor': 'ref'}) if partner_ids else ctx
            partner_ids += self.search([('name', operator, name)] + args, limit=limit)
            if not partner_ids and len(name.split()) >= 2:
                # Separating zip, email and name of partner for searching
                operand1, operand2 = name.split(' ', 1)  # name can contain spaces e.g. OpenERP S.A.
                partner_ids = self.search([('zip', operator, operand1), ('name', operator, operand2)] + args,
                                  limit=limit)
                ctx.update({'searchFor': 'zip'}) if partner_ids else ctx
                if not partner_ids:
                    partner_ids = self.search([('ref', operator, operand1), ('name', operator, operand2)] + args,
                                              limit=limit)
                    ctx.update({'searchFor': 'ref'}) if partner_ids else ctx
            if partner_ids:
                return self.with_context(ctx).name_get_custom_ref(list(set(partner_ids)))
            # else:
            #     return []

        return super(ResPartner, self).name_search(name, args, operator=operator, limit=limit)
