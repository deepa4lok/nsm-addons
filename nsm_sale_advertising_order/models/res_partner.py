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