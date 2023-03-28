# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2017 Magnus (<http://www.magnus.nl>). All Rights Reserved
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
import odoo.addons.decimal_precision as dp
from odoo.exceptions import UserError
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
from odoo.addons.queue_job.job import job, related_action
from odoo.addons.queue_job.exception import FailedJobError
from unidecode import unidecode
import datetime
from suds.plugin import MessagePlugin
from lxml import etree
from dicttoxml import dicttoxml


def xmlpprint(xml):
    return etree.tostring(etree.fromstring(xml), pretty_print=True)




class SaleOrder(models.Model):
    _inherit = ["sale.order"]

    @api.depends('order_line.line_ad4all_allow','order_line.no_copy_chase' )
    @api.multi
    def _ad4all_allow(self):
        for order in self:
            order.order_ad4all_allow = False
            for line in order.order_line:
                if line.line_ad4all_allow:
                    order.order_ad4all_allow = True
                    break

    @api.depends('date_sent_ad4all', 'write_date')
    @api.multi
    def _ad4all_write_after_sent(self):
        for order in self:
            if order.date_sent_ad4all:
                order.ad4all_write_after_sent = order.date_sent_ad4all < order.write_date

    @api.depends('order_line.ad4all_sent')
    @api.multi
    def _ad4all_sent(self):
        for order in self:
            order.ad4all_sent = False
            for line in order.order_line:
                if line.ad4all_sent:
                    order.ad4all_sent = True
                    break


    order_ad4all_allow = fields.Boolean(
        compute=_ad4all_allow,
        default=False,
        store=True,
        string='Allow to Ad4all',
        copy=False
    )
    no_copy_chase = fields.Boolean(
        compute=_ad4all_allow,
        default=False,
        store=True,
        string='No Copy Chase',
        copy=False
    )
    date_sent_ad4all = fields.Datetime(
        'Datetime Sent to Ad4all',
        index=True,
        copy=False,
        help="Datetime on which sales order is sent to Ad4all."
    )
    ad4all_write_after_sent = fields.Boolean(
        compute=_ad4all_write_after_sent,
        search='_ad4all_write_after_sent_search',
        string='Written after transferred to Ad4all',
        default=False,
        store=True,
        copy=False
    )
    ad4all_tbu = fields.Boolean(
        string='Ad4all to be updated',
        default=False,
        copy=False
    )
    ad4all_sent = fields.Boolean(
        compute=_ad4all_sent,
        string='Order to Ad4all',
        default=False,
        store=True,
        copy=False
    )
    publog_id = fields.Many2one(
        'sofrom.odooto.ad4all',
        copy=False
    )

    @job
    @api.multi
    def action_ad4all(self, arg, xml=False):
        for order in self.filtered(
                lambda s: s.state == 'sale' and s.advertising):
            res = order.transfer_order_to_ad4all(arg)
            if order.order_ad4all_allow:
                order.with_context(no_checks=True).write({'ad4all_tbu': True})
                res.with_delay(
                    description=res.reference
                ).wsdl_content(xml=xml)
        return True

    @api.multi
    def action_ad4all_xml(self):
        self.action_ad4all('update', True)

    @api.multi
    def action_ad4all_no_xml(self):
        self.action_ad4all('update', False)

    @api.multi
    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        self.action_ad4all('update', False)
        return res

    @api.multi
    def write(self, vals):
        res = super(SaleOrder, self).write(vals)
        for order in self.filtered(lambda s: s.advertising and s.state == 'sale'):
            if ('published_customer' in vals) or ('partner_id' in vals) or ('customer_contact' in vals) or ('advertising_agency'in vals) \
                                              or ('opportunity_subject' in vals) or ('order_line' in vals):
                order.action_ad4all('update', False)
        return res

    @api.multi
    def action_cancel(self):
        self.action_ad4all('delete', False)
        return super(SaleOrder, self).action_cancel()

    @api.multi
    def transfer_order_to_ad4all(self, arg):
        self.ensure_one()
        if not self.order_ad4all_allow and not self.ad4all_sent:
            vals = {
                'sale_order_id': self.id,
                'order_name': self.name,
                'reference': 'This Order will not be sent to Ad4all',
            }
            res = self.env['sofrom.odooto.ad4all'].sudo().create(vals)
        else:
            if not self.material_contact_person:
                raise UserError(
                    _('You have to fill in a material contact person.\n'
                      'Be aware, that the contact must have email and phone filled in.'))
            vals = {
                'sale_order_id': self.id,
                'order_name': self.name or '',
                'reference':
                    'Subject:' +
                    unidecode(self.opportunity_subject or '') +
                    '\n' +
                    'Order Nr.:' +
                    unidecode(self.name or ''),
                'so_customer_id': self.published_customer.ref,
                'so_customer_name': self.published_customer.name,
                'so_customer_address_street':
                    self.published_customer.street or '',
                'so_customer_address_zip':
                    self.published_customer.zip or '',
                'so_customer_address_city':
                    self.published_customer.city or '',
                'so_customer_address_phone':
                    self.published_customer.phone or '',
                'so_customer_contacts_contact_id':
                    self.material_contact_person.ref or False,
                'so_customer_contacts_contact_name':
                    self.material_contact_person.name or False,
                'so_customer_contacts_contact_email':
                    self.material_contact_person.email or False,
                'so_customer_contacts_contact_phone':
                    self.material_contact_person.phone or
                    self.material_contact_person.mobile or False,
                'so_customer_contacts_contact_type': '',
                'so_customer_contacts_contact_language': 'NL'
            }
            for key, value in vals.iteritems():
                if value == False:
                    raise UserError(_(
                        'Field %s is required in AdPortal, but has value False'
                    ) % (key))

            res = self.env['sofrom.odooto.ad4all'].sudo().create(vals)
            for line in self.order_line:
                del_param = False
                if not (line.line_ad4all_allow or line.ad4all_sent):
                    continue
                elif int(line.product_uom_qty) == 0 or arg == 'delete' or (line.ad4all_sent and not line.line_ad4all_allow):
                    del_param = True
                lvals = {
                        'so_id': res.id,
                        'odoo_order_line': line.id,
                        'advert_id': line.id,
                        'mat_id': line.id if not line.recurring else
                                                            line.recurring_id,
                        'adgr_orde_id': self.id,
                        'cancelled': del_param,
                        'herplaats': line.recurring,
                        'materialtype': line.ad_class.ad4all_material_type,
                        'sales': unidecode(self.user_id.name),
                        'sales_mail': self.user_id.email,
                        'reminder': not line.no_copy_chase,
                        'format_id': line.product_template_id.name,
                        'format_height': line.product_id.height or False,
                        'format_trim_height': line.product_id.height or False,
                        'format_width': line.product_id.width or False,
                        'format_trim_width': line.product_id.width or False,
                        'format_spread': line.product_template_id.spread,
                        'paper_pub_date': line.issue_date or line.from_date,
                        'paper_deadline': line.adv_issue.deadline or '',
                        'paper_id': line.title.code,
                        'paper_name': line.title.name,
                        'paper_issuenumber': line.adv_issue.name,
                        'placement_adclass': line.ad_class.name,
                        'placement_notice': unidecode(line.layout_remark or ''),
                        'placement_description': unidecode(
                                                    line.product_id.name or '')
                                                 + '\n' +
                                                 unidecode(line.name or ''),
                        'placement_position': unidecode(line.page_reference
                                                        or ''),
                }
                self.env['soline.from.odooto.ad4all'].sudo().create(lvals)
        return res

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"


    @api.depends('ad_class', 'adv_issue')
    def _compute_allowed(self):
        for line in self.filtered('advertising'):
            res = False
            if line.ad_class.ad4all and line.adv_issue.medium.ad4all:
                res = True
            line.line_ad4all_allow = res


    ad4all_sent = fields.Boolean(
        'Order Line sent to Ad4all',
        copy=False
    )
    line_ad4all_allow = fields.Boolean(
        compute='_compute_allowed',
        string='Ad4all Allowed',
        store=True,
        copy=False
    )
    recurring = fields.Boolean(
        'Recurring Advertisement'
    )
    no_copy_chase = fields.Boolean(
        'No Copy Chasing',
        default=False
    )
    recurring_id = fields.Many2one(
        'sale.order.line',
        string='Recurring Order Line',
    )

    @api.multi
    def unlink(self):
        if self.filtered('ad4all_sent'):
            raise UserError(
                _('You can not remove a sale order line after it has been'
                  ' sent to Ad4all.\n'
                  'Discard changes and try setting the quantity to 0.'))
        return super(SaleOrderLine, self).unlink()


class SofromOdootoAd4all(models.Model):
    _name = 'sofrom.odooto.ad4all'
    _order = 'create_date desc'

    @api.depends('ad4all_so_line.ad4all_response')
    @api.multi
    def _compute_response(self):
        for so in self:
            so.so_ad4all_response = True
            for line in so.ad4all_so_line:
                if line.ad4all_response != 200:
                    so.so_ad4all_response = False
                    break

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order'
    )
    so_ad4all_response = fields.Boolean(
        compute=_compute_response,
        default=False,
        store=True,
        string='Ad4all Response'
    )
    so_ad4all_environment = fields.Char(
        'Ad4all Environment'
    )
    json_message = fields.Text(
        'XML message'
    )
    reply_message = fields.Text(
        'Reply message'
    )
    ad4all_so_line = fields.One2many(
        'soline.from.odooto.ad4all',
        'so_id',
        string='Order Lines',
        copy=False
    )
    order_name = fields.Char(
        'Order Description'
    )
    reference = fields.Char(
        'Order Reference'
    )
    # so_customer_id = fields.Integer(
    #     string='Advertiser Number'
    # )
    so_customer_id = fields.Char(
        string='Advertiser Number'
    )
    so_customer_name = fields.Char(
        string='Advertiser Name',
        size=64
    )
    # so_customer_contacts_contact_id = fields.Integer(
    #     string='Advertiser Contact ID',
    # )
    so_customer_contacts_contact_id = fields.Char(
        string='Advertiser Contact ID',
    )
    so_customer_contacts_contact_name = fields.Char(
        string='Advertiser Contact Name',
        size=64
    )
    so_customer_contacts_contact_email = fields.Char(
        string='Advertiser Contact Email',
        size=64
    )
    so_customer_contacts_contact_phone = fields.Char(
        string='Advertiser Contact Phone',
        size=64
    )
    so_customer_contacts_contact_type = fields.Char(
        string='Advertiser Contact Type',
        size=64
    )
    so_customer_contacts_contact_language = fields.Char(
        string='Advertiser Contact Language',
        size=16,
        default='NL'
    )
    so_customer_contacts_contact2_id = fields.Integer(
        string='Advertiser Contact2 ID',
    )
    so_customer_contacts_contact2_name = fields.Char(
        string='Advertiser Contact2 Name',
        size=64
    )
    so_customer_contacts_contact2_email = fields.Char(
        string='Advertiser Contact2 Email',
        size=64
    )
    so_customer_contacts_contact2_phone = fields.Char(
        string='Advertiser Contact2 Phone',
        size=64
    )
    so_customer_contacts_contact2_type = fields.Char(
        string='Advertiser Contact2 Type',
        size=64
    )
    so_customer_contacts_contact2_language = fields.Char(
        string='Advertiser Contact2 Language',
        size=16,
        default='NL'
    )
    so_customer_address_street = fields.Char(
        string='Advertiser Address Street',
        size=64
    )
    so_customer_address_zip = fields.Char(
        string='Advertiser Address Zip Code',
        size=32
    )
    so_customer_address_city = fields.Char(
        string='Advertiser Address City',
        size=64
    )
    so_customer_address_phone = fields.Char(
        string='Advertiser Address Phone',
        size=64
    )
    so_agency = fields.Boolean(
        string='Agency'
    )
    so_media_agency_code = fields.Char(
        string='Agency Number',
        size=32
    )
    so_media_agency_name = fields.Char(
        string='Agency Name',
        size=64
    )
    so_media_agency_email = fields.Char(
        string='Agency Email',
        size=64
    )
    so_media_agency_phone = fields.Char(
        string='Agency Email',
        size=64
    )
    so_media_agency_language = fields.Char(
        string='Agency Language',
        size=16,
        default='NL'
    )
    so_media_agency_contacts_contact_id = fields.Char(
        string='Agency Contact Number',
        size=32
    )
    so_media_agency_contacts_contact_name = fields.Char(
        string='Agency Contact Name',
        size=64
    )
    so_media_agency_contacts_contact_email = fields.Char(
        string='Agency Contact Email',
        size=64
    )
    so_media_agency_contacts_contact_phone = fields.Char(
        string='Agency Contact Phone',
        size=64
    )
    so_media_agency_contacts_contact_type = fields.Char(
        string='Agency Contact Type',
        size=64
    )
    so_media_agency_contacts_contact_language = fields.Char(
        string='Agency Contact Language',
        size=16,
        default='NL'
    )
    so_media_agency_contacts_contact2_id = fields.Char(
        string='Agency Contact2 Number',
        size=32
    )
    so_media_agency_contacts_contact2_name = fields.Char(
        string='Agency Contact2 Name',
        size=64
    )
    so_media_agency_contacts_contact2_email = fields.Char(
        string='Agency Contact2 Email',
        size=64
    )
    so_media_agency_contacts_contact2_phone = fields.Char(
        string='Agency Contact2 Phone',
        size=64
    )
    so_media_agency_contacts_contact2_type = fields.Char(
        string='Agency Contact2 Type',
        size=64
    )
    so_media_agency_contacts_contact2_language = fields.Char(
        string='Agency Contact2 Language',
        size=16,
        default='NL'
    )

    @job
    def wsdl_content(self, xml=False):
        self.ensure_one()
        if self.so_ad4all_response:
            raise UserError(_(
                'This Sale Order already has been succesfully sent to Ad4all.'))
        for line in self.ad4all_so_line:
            response = line.call_wsdl(xml)
            if response['code'] == 200:
                self.env['sale.order.line'].search(
                    [('id', '=', line.advert_id)]).write(
                    {'ad4all_sent': True})
            else:
                #If error/failure, try to send other lines
                continue
        so = self.env['sale.order'].search(
            [('id', '=', self.sale_order_id.id)])
        sovals = {'date_sent_ad4all': datetime.datetime.now(),
                  'publog_id': self.id,
                  'ad4all_tbu': False
                  }
        so.with_context(no_checks=True).write(sovals)
        wsdl = "https://portal.ad4all.nl/data/wsdl"
        self.so_ad4all_environment = wsdl
        return True


    def update_fields_value(self):
        # for advertsing with title
        sql = ("UPDATE sofrom_odooto_ad4all "
               "SET so_customer_id =  so_customer_id_moved0, "
               "so_customer_contacts_contact_id = so_customer_contacts_contact_id_moved0"
               )
        cr = self.env.cr
        cr.execute(sql)

        sql = ("UPDATE soline_from_odooto_ad4all "
               "SET paper_id = paper_id_moved0"
               )
        cr = self.env.cr
        cr.execute(sql)



class SoLinefromOdootoAd4all(models.Model):
    _name = 'soline.from.odooto.ad4all'

    so_id = fields.Many2one(
        'sofrom.odooto.ad4all',
        string='so_from_Reference',
        ondelete='cascade',
        required=True,
        copy=False
    )
    odoo_order_line = fields.Many2one(
        'sale.order.line',
        string='Order Line Reference',
        ondelete='cascade',
        required=False,
        index=True,
        copy=False
    )
    ad4all_response = fields.Text(
        'Ad4all Response'
    )
    json_message = fields.Text(
        'XML message'
    )
    reply_message = fields.Text(
        'Reply message'
    )
    portal = fields.Char(
        string='Ad4all Portal'
    )
    deliverer = fields.Char(
        string='Ad4all Deliverer'
    )
    order_code = fields.Char(
        string='Ad4all Order Code'
    )
    advert_id = fields.Integer(
        string='Line ID'
    )
    mat_id = fields.Integer(
        string='Material ID'
    )
    adgr_orde_id = fields.Many2one(
        'sale.order',
        string='Sale Order ID'
    )
    adkind = fields.Char(
        string='Advertising Type',
        default="PRINT"
    )
    adstatus = fields.Char(
        string='Advertising Status',
        default="Nieuw"
    )
    cancelled = fields.Boolean(
        string='Cancelled'
    )
    herplaats = fields.Boolean(
        string='Herplaatsing'
    )
    materialtype = fields.Char(
        string='Material Type',
        default="PRINT"
    )
    format_id = fields.Char(
        string='Product ID'
    )
    format_height = fields.Integer(
        string='Page Height mm'
    )
    format_width = fields.Integer(
        string='Page Width mm'
    )
    format_trim_height = fields.Integer(
        string='Print Height mm'
    )
    format_trim_width = fields.Integer(
        string='Print Width mm'
    )
    format_spread = fields.Boolean(
        string='Spread'
    )
    paper_pub_date = fields.Date(
        string='Issue Date'
    )
    paper_deadline = fields.Date(
        string='Deadline Date'
    )
    # paper_id = fields.Integer(
    #     string='Title Id'
    # )
    paper_id = fields.Char(
        string='Title Id'
    )
    paper_name = fields.Char(
        string='Advertising Title Name',
        size=64
    )
    paper_issuenumber = fields.Char(
        string='Advertising Issue Name',
        size=64
    )
    placement_adclass = fields.Char(
        string='Advertising Class Name',
        size=64
    )
    placement_description = fields.Char(
        string='Advertising Description',
        size=254
    )
    placement_notice = fields.Char(
        string='Material Remarks'
    )
    placement_position = fields.Char(
        string='Mapping Remarks'
    )
    sales = fields.Char(
        string='User Name',
        size=32
    )
    sales_mail = fields.Char(
        string='User Email',
        size=64
    )
    reminder = fields.Boolean(
        string='Reminder'
    )
    # customer_id = fields.Integer(
    #     related='so_id.so_customer_id',
    #     string='Advertiser Number'
    # )
    customer_id = fields.Char(
        related='so_id.so_customer_id',
        string='Advertiser Number'
    )
    customer_name = fields.Char(
        related='so_id.so_customer_name',
        string='Advertiser Name',
        size=64
    )
    # customer_contacts_contact_id = fields.Integer(
    #     related='so_id.so_customer_contacts_contact_id',
    #     string='Advertiser Contact ID',
    # )
    customer_contacts_contact_id = fields.Char(
        related='so_id.so_customer_contacts_contact_id',
        string='Advertiser Contact ID',
    )
    customer_contacts_contact_name = fields.Char(
        related='so_id.so_customer_contacts_contact_name',
        string='Advertiser Contact Name',
        size=64
    )
    customer_contacts_contact_email = fields.Char(
        related='so_id.so_customer_contacts_contact_email',
        string='Advertiser Contact Email',
        size=64
    )
    customer_contacts_contact_phone = fields.Char(
        related='so_id.so_customer_contacts_contact_phone',
        string='Advertiser Contact Phone',
        size=64
    )
    customer_contacts_contact_type = fields.Char(
        related='so_id.so_customer_contacts_contact_type',
        string='Advertiser Contact Type',
        size=64
    )
    customer_contacts_contact_language = fields.Char(
        related='so_id.so_customer_contacts_contact_language',
        string='Advertiser Contact Language',
        size=16,
    )
    customer_contacts_contact2_id = fields.Integer(
        related='so_id.so_customer_contacts_contact2_id',
        string='Advertiser Contact2 ID',
    )
    customer_contacts_contact2_name = fields.Char(
        related='so_id.so_customer_contacts_contact2_name',
        string='Advertiser Contact2 Name',
        size=64
    )
    customer_contacts_contact2_email = fields.Char(
        related='so_id.so_customer_contacts_contact2_email',
        string='Advertiser Contact2 Email',
        size=64
    )
    customer_contacts_contact2_phone = fields.Char(
        related='so_id.so_customer_contacts_contact2_phone',
        string='Advertiser Contact2 Phone',
        size=64
    )
    customer_contacts_contact2_type = fields.Char(
        related='so_id.so_customer_contacts_contact2_type',
        string='Advertiser Contact2 Type',
        size=64
    )
    customer_contacts_contact2_language = fields.Char(
        related='so_id.so_customer_contacts_contact2_language',
        string='Advertiser Contact2 Language',
        size=16,
        default='nl'
    )
    customer_address_street = fields.Char(
        related='so_id.so_customer_address_street',
        string='Advertiser Address Street',
        size=64
    )
    customer_address_zip = fields.Char(
        related='so_id.so_customer_address_zip',
        string='Advertiser Address Zip Code',
        size=32
    )
    customer_address_city = fields.Char(
        related='so_id.so_customer_address_city',
        string='Advertiser Address City',
        size=64
    )
    customer_address_phone = fields.Char(
        related='so_id.so_customer_address_phone',
        string='Advertiser Address Phone',
        size=64
    )
    agency = fields.Boolean(
        related='so_id.so_agency',
        string='Agency'
    )
    media_agency_code = fields.Char(
        related='so_id.so_media_agency_code',
        string='Agency Number',
        size=32
    )
    media_agency_name = fields.Char(
        related='so_id.so_media_agency_name',
        string='Agency Name',
        size=64
    )
    media_agency_email = fields.Char(
        related='so_id.so_media_agency_email',
        string='Agency Email',
        size=64
    )
    media_agency_phone = fields.Char(
        related='so_id.so_media_agency_phone',
        string='Agency Email',
        size=64
    )
    media_agency_language = fields.Char(
        related='so_id.so_media_agency_language',
        string='Agency Language',
        size=16,
        default='nl'
    )
    media_agency_contacts_contact_id = fields.Char(
        related='so_id.so_media_agency_contacts_contact_id',
        string='Agency Contact Number',
        size=32
    )
    media_agency_contacts_contact_name = fields.Char(
        related='so_id.so_media_agency_contacts_contact_name',
        string='Agency Contact Name',
        size=64
    )
    media_agency_contacts_contact_email = fields.Char(
        related='so_id.so_media_agency_contacts_contact_email',
        string='Agency Contact Email',
        size=64
    )
    media_agency_contacts_contact_phone = fields.Char(
        related='so_id.so_media_agency_contacts_contact_phone',
        string='Agency Contact Phone',
        size=64
    )
    media_agency_contacts_contact_type = fields.Char(
        related='so_id.so_media_agency_contacts_contact_type',
        string='Agency Contact Type',
        size=64
    )
    media_agency_contacts_contact_language = fields.Char(
        related='so_id.so_media_agency_contacts_contact_language',
        string='Agency Contact Language',
        size=16,
        default='nl'
    )
    media_agency_contacts_contact2_id = fields.Char(
        related='so_id.so_media_agency_contacts_contact2_id',
        string='Agency Contact2 Number',
        size=32
    )
    media_agency_contacts_contact2_name = fields.Char(
        related='so_id.so_media_agency_contacts_contact2_name',
        string='Agency Contact2 Name',
        size=64
    )
    media_agency_contacts_contact2_email = fields.Char(
        related='so_id.so_media_agency_contacts_contact2_email',
        string='Agency Contact2 Email',
        size=64
    )
    media_agency_contacts_contact2_phone = fields.Char(
        related='so_id.so_media_agency_contacts_contact2_phone',
        string='Agency Contact2 Phone',
        size=64
    )
    media_agency_contacts_contact2_type = fields.Char(
        related='so_id.so_media_agency_contacts_contact2_type',
        string='Agency Contact2 Type',
        size=64
    )
    media_agency_contacts_contact2_language = fields.Char(
        related='so_id.so_media_agency_contacts_contact2_language',
        string='Agency Contact2 Language',
        size=16,
        default='nl'
    )
    creative_agency_code = fields.Char(
        string='Creative Number',
        size=32
    )
    creative_agency_name = fields.Char(
        string='Creative Name',
        size=64
    )
    creative_agency_email = fields.Char(
        string='Creative Email',
        size=64
    )
    creative_agency_phone = fields.Char(
        string='Creative Email',
        size=64
    )
    creative_agency_language = fields.Char(
        string='Creative Language',
        size=16,
        default='nl'
    )
    creative_agency_contacts_contact_id = fields.Char(
        string='Creative Contact Number',
        size=32
    )
    creative_agency_contacts_contact_name = fields.Char(
        string='Creative Contact Name',
        size=64
    )
    creative_agency_contacts_contact_email = fields.Char(
        string='Creative Contact Email',
        size=64
    )
    creative_agency_contacts_contact_phone = fields.Char(
        string='Creative Contact Phone',
        size=64
    )
    creative_agency_contacts_contact_type = fields.Char(
        string='Creative Contact Type',
        size=64
    )
    creative_agency_contacts_contact_language = fields.Char(
        string='Creative Contact Language',
        size=16,
        default='nl'
    )

    def call_wsdl(self, xml=False):
        self.ensure_one()
        session = Session()
        user = 'nsm'
        password = 'H2hP7#9d2gmN48gB'
        session.auth = HTTPBasicAuth(user, password)
        settings = Settings(strict=False, xml_huge_tree=True)
        wsdl = "https://portal.ad4all.nl/data/wsdl"
        history = HistoryPlugin()
        client = Client(
            wsdl,
            transport=Transport(session=session),
            settings=settings,
            plugins=[history]
        )
        Order = client.type_factory('ns0')
        order_obj = Order.order(
            portal="nsm_L8hd6Ep",
            deliverer="nsm",
            order_code=int(float(self.adgr_orde_id.id))
        )
        paper_deadline = datetime.datetime.strptime(
            self.paper_deadline, '%Y-%m-%d').strftime('%Y%m%d') \
            if self.paper_deadline else ''
        paper_pub_date = datetime.datetime.strptime(
            self.paper_pub_date, '%Y-%m-%d').strftime(
            '%Y%m%d') if self.paper_pub_date else ''
        xml_dict = [{
            'root': [
                {'advert_id': int(float(self.advert_id))},
                {'id': int(float(self.mat_id))},
                {'adgr_orde_id': int(float(self.adgr_orde_id.id))},
                {'adkind': self.adkind},
                {'adstatus': self.adstatus},
                {'cancelled': "Yes" if self.cancelled else "No"},
                {'herplaats': "Yes" if self.herplaats else "No"},
                {'materialtype': self.materialtype},
                {'sales': self.sales},
                {'sales_mail': self.sales_mail},
                {'reminder': "Yes" if self.reminder else "No"},
                {'format': [
                    {'id': self.format_id},
                    {'height': int(float(self.format_height))},
                    {'width': int(float(self.format_width))},
                    {'trim_height': int(float(self.format_trim_height))},
                    {'trim_width': int(float(self.format_trim_width))},
                    {'spread': "Yes" if self.format_spread else "No"},
                ]},
                {'paper': [
                    {'pub_date': paper_pub_date},
                    {'deadline': paper_deadline},
                    {'id': self.paper_id},
                    {'name': self.paper_name},
                    {'issuenumber': self.paper_issuenumber},
                ]},
                {'placement': [
                    {'adclass': self.placement_adclass},
                    {'description': self.placement_description},
                    {'notice': self.placement_notice},
                    {'position': self.placement_position},
                ]},
            ]
        }]

        customer_dict = {'customer': [
            {'id': self.customer_id},
            {'name': self.customer_name},
            {'address': [
                {'street': self.customer_address_street},
                {'zip': self.customer_address_zip},
                {'city': self.customer_address_city},
                {'phone': self.customer_address_phone},
            ]},
        ]}

        if self.customer_contacts_contact_id:
            contacts_data = [{
                'contact': [
                    {'id': self.customer_contacts_contact_id},
                    {'name': self.customer_contacts_contact_name},
                    {'email': self.customer_contacts_contact_email},
                    {'phone': self.customer_contacts_contact_phone},
                    {'type': self.customer_contacts_contact_type},
                    {'language': self.customer_contacts_contact_language},
                ]
            }]
            if self.customer_contacts_contact2_id:
                contact2_data = {
                    'contact': [
                        {'id': self.customer_contacts_contact2_id},
                        {'name': self.customer_contacts_contact2_name},
                        {'email': self.customer_contacts_contact2_email},
                        {'phone': self.customer_contacts_contact2_phone},
                        {'type': self.customer_contacts_contact2_type},
                        {'language': self.customer_contacts_contact2_language},
                    ]
                }
                contacts_data.append(contact2_data)
            customer_dict['customer'].append({'contacts': contacts_data})
        xml_dict[0]['root'].append(customer_dict)

        if self.agency:
            media_data = {'media_agency': [
                {'code': self.media_agency_code},
                {'name': self.media_agency_name},
                {'email': self.media_agency_email},
                {'phone': self.media_agency_phone},
                {'language': self.media_agency_language},
                ]
            }
            if self.media_agency_contacts_contact_id:
                agency_contacts_data = [{
                        'contact': [
                            {'id': self.media_agency_contacts_contact_id},
                            {'name': self.media_agency_contacts_contact_name},
                            {'email': self.media_agency_contacts_contact_email},
                            {'phone': self.media_agency_contacts_contact_phone},
                            {'type': self.media_agency_contacts_contact_type},
                            {'language': self.media_agency_contacts_contact_language},
                        ],
                    }]
                if self.media_agency_contacts_contact2_id:
                    agency_contacts2_data = {
                            'contact': [
                                {'id': self.media_agency_contacts_contact2_id},
                                {'name': self.media_agency_contacts_contact2_name},
                                {'email': self.media_agency_contacts_contact2_email},
                                {'phone': self.media_agency_contacts_contact2_phone},
                                {'type': self.media_agency_contacts_contact2_type},
                                {'language': self.media_agency_contacts_contact2_language},
                            ],
                        },
                    agency_contacts_data.append(agency_contacts2_data)
                media_data['media_agency'].append({'contacts': agency_contacts_data})
            xml_dict[0]['root'].append(media_data)

        xmlData = dicttoxml(xml_dict, attr_type=False, root=False)
        xmlData = (xmlData.replace('<item>', '')).replace('<item >', '').replace('</item>', '')
        order_obj.xml_data = xmlpprint(xmlData)
        try:
            response = client.service.soap_order(order=order_obj)
            self.write({
                'ad4all_response': response['code'],
                'json_message': order_obj.xml_data,
        })
        except Exception as e:
            raise FailedJobError(
                _('Error wsdl call: %s') % (e))
        return response

