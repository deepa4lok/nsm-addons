from odoo import api, fields, models, _
from datetime import datetime, date
from odoo import exceptions
import base64
from odoo.addons.queue_job.job import job, related_action
from odoo.addons.queue_job.exception import FailedJobError
import xmltodict
import requests
from requests.auth import HTTPBasicAuth
from odoo.exceptions import UserError
from collections import OrderedDict
import re


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.depends('invoice_line_ids.roularta_sent')
    @api.multi
    def _roularta_sent(self):
        for inv in self:
            inv.roularta_sent = False
            for line in inv.invoice_line_ids:
                if line.roularta_sent:
                    inv.roularta_sent = True
                    break

    roularta_sent = fields.Boolean(
        compute=_roularta_sent,
        string='Invoice Line sent to Roularta',
        default=False,
        store=True,
        copy=False
    )

    date_sent_roularta = fields.Datetime(
        'Datetime Sent to roularta',
        index=True,
        copy=False,
        help="Datetime on which Invoice is sent to roularta."
    )

    roularta_log_id = fields.Many2one(
        'move.odooto.roularta',
        copy=False
    )

    partner_ref = fields.Char(related='partner_id.ref', string='Partner Ref#', readonly=True, store=True)

    @api.multi
    def action_cancel(self):
        res = super(AccountInvoice, self).action_cancel()
        self.invoice_line_ids.write({'roularta_sent': False})
        return res

    @api.multi
    def action_roularta_interface(self):
        for inv in self:
            sale_invoice = inv.invoice_line_ids.mapped('sale_order_id')
            if ((sale_invoice and inv.ad) or (not sale_invoice and inv.type in ('out_invoice', 'out_refund')))\
                    or inv.type in ('in_invoice', 'in_refund'):
                inv.with_delay(
                    description=inv.number
                ).transfer_invoice_to_roularta()

    def parse_document_type(self):
        doc_type = ''
        short_name = ''
        type = self.type
        if type in ('out_invoice', 'out_refund'):
            doc_type += 'V'
            short_name += 'Verkoopfact'
        elif type in ('in_invoice', 'in_refund'):
            doc_type += 'I'
            short_name += 'Inkoopfact'

        if type in ('out_invoice', 'in_invoice'):
            doc_type += 'F'
        elif type in ('out_refund', 'in_refund'):
            doc_type += 'C'
            short_name += ' '+'cn'

        #domestic tax code with no external id
        domestic_tax_name = ['Verkopen/omzet laag 6%','BTW te vorderen laag (6% oud) (inkopen)','Verkopen/omzet laag 9% (incl.)', 'BTW te vorderen 0%']

        #domestic tax code with external_id
        domestic_xml_ext_ids = ['l10n_nl.1_btw_21', 'l10n_nl.1_btw_21_buy','l10n_nl.1_btw_21_d','l10n_nl.1_btw_21_buy_d','l10n_nl.1_btw_21_buy_incl',
                                'l10n_nl.1_btw_0','l10n_nl.1_btw_6','l10n_nl.1_btw_0_d','l10n_nl.1_btw_6_d','l10n_nl.1_btw_6_buy',
                                'l10n_nl.1_btw_6_buy_incl','l10n_nl.1_btw_6_buy_d','l10n_nl.1_btw_overig','l10n_nl.1_btw_overig_d',
                                'l10n_nl.1_btw_overig_buy','l10n_nl.1_btw_overig_buy_d','l10n_nl.1_btw_verk_0','l10n_nl.1_btw_ink_0',
                                'l10n_nl.1_btw_ink_0_1', 'l10n_nl.1_btw_ink_0_2']

        # EU tax ext code
        EU_xml_ext_ids = ['l10n_nl.1_btw_I_6', 'l10n_nl.1_btw_I_21', 'l10n_nl.1_btw_I_overig', 'l10n_nl.1_btw_X0', 'l10n_nl.1_btw_X2',
                          'l10n_nl.1_btw_I_6_d', 'l10n_nl.1_btw_I_21_d', 'l10n_nl.1_btw_I_overig_d', 'l10n_nl.1_btw_I_6_1', 'l10n_nl.1_btw_I_21_1',
                        'l10n_nl.1_btw_I_6_d_1', 'l10n_nl.1_btw_I_21_d_1', 'l10n_nl.1_btw_I_6_2', 'l10n_nl.1_btw_I_21_2', 'l10n_nl.1_btw_I_6_d_2',
                        'l10n_nl.1_btw_I_21_d_2', 'l10n_nl.1_btw_I_overig_2', 'l10n_nl.1_btw_I_overig_d_2', 'l10n_nl.1_btw_I_overig_1', 'l10n_nl.1_btw_I_overig_d_1']

        # Outside EU tax ext code
        OEU_xml_ext_ids = ['l10n_nl.1_btw_E1', 'l10n_nl.1_btw_E2', 'l10n_nl.1_btw_E_overig', 'l10n_nl.1_btw_X1',
                           'l10n_nl.1_btw_E1_d', 'l10n_nl.1_btw_E2_d', 'l10n_nl.1_btw_E_overig_d', 'l10n_nl.1_btw_E1_1',
                           'l10n_nl.1_btw_E2_1', 'l10n_nl.1_btw_E_overig_1', 'l10n_nl.1_btw_X3', 'l10n_nl.1_btw_E1_d_1',
                           'l10n_nl.1_btw_E2_d_1', 'l10n_nl.1_btw_E_overig_d_1', 'l10n_nl.1_btw_E1_2', 'l10n_nl.1_btw_E2_2',
                           'l10n_nl.1_btw_E_overig_2', 'l10n_nl.1_btw_E1_d_2', 'l10n_nl.1_btw_E2_d_2', 'l10n_nl.1_btw_E_overig_d_2']

        # if len(self.tax_line_ids.ids) > 1:
        #     raise UserError(_("Cant't send to roularta! More than one tax line!"))
        tax_dic = {}
        for tax_line in self.tax_line_ids:
            d_type = doc_type
            s_name = short_name
            tax = tax_line.tax_id
            tax_amt = '0'+str(int(tax.amount)) if len(str(int(tax.amount))) == 1 else str(int(tax.amount))
            if tax.name in domestic_tax_name:
                d_type += 'L'+tax_amt
                s_name += ' '+'loc'+' '+tax_amt
            else:
                model_data = self.env['ir.model.data']
                res = model_data.search([('module', '=', 'l10n_nl'), ('model', '=', 'account.tax'), ('res_id', '=', tax.id)])
                if res:
                    ext_id_ref = res.module+'.'+res.name
                    if ext_id_ref in domestic_xml_ext_ids:
                        d_type += 'L' + tax_amt
                        s_name += ' ' + 'loc' + ' ' + tax_amt
                    elif ext_id_ref in OEU_xml_ext_ids:
                        d_type += 'X' + tax_amt
                        s_name += ' ' + 'uitvoer'
                    elif ext_id_ref in EU_xml_ext_ids:
                        d_type += 'I' + tax_amt
                        s_name += ' ' + 'IC' + ' ' + tax_amt
                else:
                    raise UserError(_('Tax document not found!'))

            tax_dic[tax_line.tax_id] = {'doc_type':d_type, 'short_name':s_name}
        return tax_dic

    @job
    def transfer_invoice_to_roularta(self):
        self.ensure_one()
        if self.roularta_sent:
            vals = {
                'invoice_id': self.id,
                'invoice_name': self.name,
                'reference': 'This Invoice will not be sent to Roularta',
                'status':'draft'
            }
            res = self.env['move.odooto.roularta'].sudo().create(vals)
            return res
        else:
            invoice_number = re.sub("[^A-Z 0-9]", "", self.number,0,re.IGNORECASE)
            tax_datas = self.parse_document_type()
            vals = {
                'invoice_id':self.id,
                'invoice_name': self.name,
                'reference': invoice_number,
                'move_id':self.move_id.id,
                'company_code':self.operating_unit_id.code,
                'code':'XXX',
                'number':invoice_number,
                'period':datetime.strptime(self.date, '%Y-%m-%d').strftime('%Y/%m'),
                'curcode':self.currency_id.id,
                'date':datetime.strptime(self.date, '%Y-%m-%d').strftime('%Y-%m-%d'),
                'status': 'draft',
            }

            summary_seq = 1
            invoice_tax_account = self.tax_line_ids.mapped('account_id')
            tax_lines = self.move_id.line_ids.filtered(lambda ml: ml.account_id in invoice_tax_account)
            tax_amt = sum(tl.credit for tl in tax_lines)
            sale_invoice = self.invoice_line_ids.mapped('sale_order_id')
            vendor_invoice = self.invoice_line_ids.mapped('purchase_id')

            move_line = self.env['move.line.odooto.roularta']
            summary_lines=[]
            operating_code = self.operating_unit_id.code
            invoice_type = self.type
            sum_line_sense = 'debit'
            if invoice_type in ('in_invoice', 'out_refund'):
                sum_line_sense = 'credit'

            #Determine partner
            partner = self.partner_id
            if partner.ref[0] == 'R':
                partner = self.partner_id
            else:
                if partner.parent_id:
                    if partner.parent_id.ref[0] == 'R':
                        partner = self.partner_id.parent_id
                    else:
                        partner = self.partner_id


            #Summary line

            for mline in self.move_id.line_ids.filtered(lambda ml: ml.account_id == self.account_id):
                UserRef1 = invoice_number
                if sale_invoice:
                    UserRef1 = 'V' + UserRef1
                elif vendor_invoice:
                    UserRef1 = 'I' + UserRef1

                if mline.debit > 0:
                    sum_line_sense = 'debit'
                else:
                    sum_line_sense = 'credit'

                msg = ''
                # partner = mline.partner_id
                # if mline.partner_id.parent_id:
                #     if mline.partner_id.parent_id.ref[0] == 'R':
                #         partner = mline.partner_id.parent_id
                #     else:
                #         msg = 'Partner parent has no RFF number. Using child.'
                # if mline.partner_id.ref[0] == 'R':
                #     partner = mline.partner_id
                # else:
                #     msg = 'Partner and Parent have no RFF number.'

                if not mline.account_id.ext_account:
                    msg += ' %s external account is missing!\n' % mline.account_id.name
                if msg:
                    raise UserError(_('%s')%msg)

                lvals = {
                    'move_line_id': mline.id,
                    'number':summary_seq,
                    'dest_code':operating_code,
                    'account_code':mline.account_id.ext_account + '.' + partner.ref,
                    'doc_value':mline.debit or mline.credit,
                    'doc_sum_tax':tax_amt,
                    'dual_rate':40.339900000,
                    'doc_rate':1.000000000,
                    'line_type':'summary',
                    # 'line_sense':"debit" if sale_invoice else "credit",
                    'line_sense':sum_line_sense,
                    'line_origin':'dl_orig_additional',
                    'due_date':datetime.strptime(mline.date, '%Y-%m-%d').strftime('%Y-%m-%d %H:%M:%S'),
                    'media_code':'BI',
                    'user_ref1':UserRef1,
                    'user_ref2':'',
                    'ext_ref1':'',
                    'ext_ref2':'',
                    'ext_ref6':'',
                }
                summary_lines.append((0, 0, lvals))
                summary_seq += 1

            # Analysis line
            ana_line_sense = 'credit'
            if invoice_type in ('in_invoice', 'out_refund'):
                ana_line_sense = 'debit'

            roularta_account_code = 'K01490'
            if invoice_type in ('in_invoice', 'in_refund'):
                roularta_account_code = 'K01410'


            for mline in self.move_id.line_ids. \
                filtered(lambda ml: ml.account_id not in (invoice_tax_account+self.account_id)):

                tax_data = tax_datas[mline.tax_ids[0]] if mline.tax_ids else {'doc_type': '', 'short_name':''}

                aa_code = mline.analytic_account_id and str(mline.analytic_account_id.code)

                if mline.debit > 0:
                    ana_line_sense = 'debit'
                else:
                    ana_line_sense = 'credit'

                taxes = mline.tax_ids.compute_all(mline.credit, mline.currency_id,
                                                  mline.quantity, mline.product_id, mline.partner_id)['taxes']
                total_tax_amount = 0.0
                for tax in taxes:
                    total_tax_amount += tax['amount']

                msg = ''
                # partner = mline.partner_id
                # if mline.partner_id.type == 'invoice':
                #     partner = mline.partner_id.parent_id
                # if not partner.ref:
                #     msg = 'Partner %s Internal Reference is missing!\n'% partner.name

                if not mline.account_id.ext_account:
                    msg += ' %s external account is missing!\n' % mline.account_id.name

                inv_line = self.invoice_line_ids.filtered(lambda inv_line: inv_line.account_id == mline.account_id and inv_line.product_id == mline.product_id)
                if inv_line and inv_line[0] and inv_line[0].so_line_id:
                    title_code = inv_line[0].so_line_id and inv_line[0].so_line_id.title and inv_line[0].so_line_id.title.code
                else:
                    if self.type in ('in_refund', 'in_invoice'):
                        aa = inv_line and inv_line[0].account_analytic_id or mline.anaytic_account_id
                        adv_issue = self.env['sale.advertising.issue'].search([('analytic_account_id', '=', aa.id)], limit=1)
                        title_code = adv_issue.code
                    else:
                        if inv_line:
                            title_code = inv_line[0].adv_issue.code
                        else:
                            adv_issue = self.env['sale.advertising.issue'].search([('analytic_account_id', '=', mline.anaytic_account_id.id)],
                                                                                  limit=1)
                            title_code = adv_issue.code

                if not title_code:
                    msg += 'Product %s title code is missing!' % mline.product_id.name

                if msg:
                    raise UserError(_('%s')%msg)

                lvals = {
                    'move_line_id': mline.id,
                    'number': summary_seq,
                    'dest_code': operating_code,
                    'account_code': mline.account_id.ext_account + '.' + partner.ref + '.' + roularta_account_code + '.' + title_code,
                    'doc_value': mline.credit or mline.debit,
                    'dual_rate': 40.339900000,
                    'doc_rate': 1.000000000,
                    'line_type': 'analysis',
                    'line_sense': ana_line_sense,
                    'line_origin': 'dl_orig_additional',
                    'due_date': datetime.strptime(mline.date, '%Y-%m-%d').strftime('%Y-%m-%d %H:%M:%S'),
                    # 'code': 'VFL21' if self.type == 'out_invoice' else 'VCL21',
                    'code': tax_data['doc_type'],
                    'short_name': tax_data['short_name'],
                    'ext_ref4': aa_code,
                    'description': mline.name,
                    'value': total_tax_amount,
                }
                summary_lines.append((0, 0, lvals))
                summary_seq += 1

            # Tax line
            for mline in self.move_id.line_ids. \
                filtered(lambda ml: ml.account_id in invoice_tax_account):

                if not mline.account_id.ext_account:
                    raise UserError(_('%s external account is missing!') % mline.account_id.name)

                lvals = {
                    'move_line_id': mline.id,
                    'number': summary_seq,
                    'dest_code': operating_code,
                    'account_code': mline.account_id.ext_account,
                    'doc_value': mline.credit or mline.debit,
                    'dual_rate': 40.339900000,
                    'doc_rate': 1.000000000,
                    'line_type': 'tax',
                    # 'line_sense': "credit" if sale_invoice else "debit",
                    'line_sense': ana_line_sense,
                    'line_origin': 'dl_orig_gentax',
                    # 'code':'VFL21' if self.type == 'out_invoice' else 'VCL21',
                    'code':tax_datas[mline.tax_line_id]['doc_type'],
                    'due_date': datetime.strptime(mline.date, '%Y-%m-%d').strftime('%Y-%m-%d %H:%M:%S'),
                    'doc_tax_turnover':self.amount_untaxed
                }
                summary_lines.append((0, 0, lvals))
                summary_seq += 1

            vals['roularta_invoice_line'] = summary_lines
            res = self.env['move.odooto.roularta'].sudo().create(vals)
            res.with_delay(
                description=res.invoice_name
            ).roularta_content()
            return

    @api.multi
    def invoice_validate(self):
        res = super(AccountInvoice, self).invoice_validate()
        self.action_roularta_interface()
        return res

    @api.multi
    def update_unit4(self):
        self.ensure_one()
        if not self.roularta_sent:
            self.action_roularta_interface()
        return

    @api.model
    def _refund_cleanup_lines(self, lines):
        """ Inherit to avoid line roularta_sent being copied
        """
        result = super(AccountInvoice, self)._refund_cleanup_lines(lines)
        if result and result[0] and result[0][2]:
            result[0][2].pop('roularta_sent', None)
        return result


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    roularta_sent = fields.Boolean(
        'Invoice Line sent to Roularta',
        copy=False
    )

    adv_issue = fields.Many2one(
        'sale.advertising.issue',
        'Advertising Issue'
    )

class MovefromOdootoRoularta(models.Model):
    _name = 'move.odooto.roularta'
    _order = 'create_date desc'
    _rec_name = 'number'

    @api.depends('roularta_invoice_line.roularta_response')
    @api.multi
    def _compute_response(self):
        for acc in self:
            acc.status = 'draft'
            acc.account_roularta_response = True
            for line in acc.roularta_invoice_line:
                acc.account_roularta_response_message = line.roularta_response_message
                acc.account_roularta_response_code = line.roularta_response
                if line.roularta_response != 200:
                    acc.account_roularta_response = False
                    acc.status = 'failed'
                elif line.roularta_response == 200:
                    acc.status = 'successful'
                break

    invoice_id = fields.Many2one(
        'account.invoice',
        "Invoice"
    )
    move_id = fields.Many2one(related='invoice_id.move_id', relation="account.move", string='Move', store=True, readonly=True)
    company_code = fields.Char('Company Code', size=16)
    code = fields.Char('Code', size=16)
    number = fields.Char('Invoice Number')
    period = fields.Char('Period', size=16)
    curcode = fields.Many2one('res.currency','CurCode')
    date = fields.Datetime('Date')
    invoice_name = fields.Char('Invoice Description')
    reference = fields.Char('Invoice Reference')
    roularta_invoice_line = fields.One2many(
        'move.line.odooto.roularta',
        'inv_id',
        string='Invoice Lines',
        copy=False
    )
    account_roularta_response = fields.Boolean(
        compute=_compute_response,
        default=False,
        store=True,
        string='Roularta Response'
    )
    account_roularta_response_message = fields.Text(
        compute=_compute_response,
        default=False,
        store=False,
        string='Roularta Response Message'
    )
    account_roularta_response_code = fields.Integer(
        compute=_compute_response,
        default=False,
        store=False,
        string='Roularta Response Code'
    )
    xml_message = fields.Text(
        'XML message'
    )

    status = fields.Selection([('draft', 'Draft'), ('successful', 'Successful'), ('failed', 'Failed')], string='Status',
                              required=True, readonly=True, store=True, compute=_compute_response)

    
    @job
    def roularta_content(self, xml=False):
        self.ensure_one()
        if self.account_roularta_response:
            raise UserError(_(
                'This Account Invoice already has been succesfully sent to Roularta.'))
        if self.roularta_invoice_line:
            response = self.roularta_invoice_line.call_roularta(self, xml)
            if response.status_code == 200:
                self.env['account.invoice.line'].search(
                    [('invoice_id', '=', self.invoice_id.id)]).write(
                    {'roularta_sent': True})
            # else:
            #     return
        acc = self.env['account.invoice'].search(
            [('id', '=', self.invoice_id.id)])
        accvals = {'date_sent_roularta': datetime.now(),
                  'roularta_log_id': self.id,
                  }
        if acc:
            acc.write(accvals)
        return True

    @api.model
    def update_roularta_status(self):
        for acc in self.search([]):
            if acc.account_roularta_response_code > 200:
                acc.status = 'failed'
            elif acc.status == 200:
                acc.status = 'successful'
            else:
                acc.status = 'draft'


class MoveLinefromOdootoRoularta(models.Model):
    _name = 'move.line.odooto.roularta'
    _order = 'create_date desc'

    move_line_id = fields.Many2one('account.move.line', "Move Line")
    number = fields.Integer(string='Sequence Number')
    dest_code = fields.Char(string='Dest Code', size=16)
    account_code = fields.Char(string='Account Code', size=64)
    doc_value = fields.Float(string='DocValue')
    doc_sum_tax = fields.Float(string='DocSumTax')
    dual_rate = fields.Float(string='Dual Rate')
    doc_rate = fields.Float(string='Doc Rate')
    line_type = fields.Char(string='Line Type', size=16)
    line_sense = fields.Char(string='Line Sense', size=16)
    line_origin = fields.Char(string='Line Origin', size=32)
    due_date = fields.Datetime('Due Date', size=16)
    media_code = fields.Char('Media Code', size=16)
    user_ref1 = fields.Char('User Ref1', size=16)
    user_ref2 = fields.Char('User Ref2', size=16)
    ext_ref1 = fields.Char('Ext Ref1', size=16)
    ext_ref2 = fields.Char('Ext Ref2', size=16)
    ext_ref4 = fields.Char('Ext Ref4', size=16)
    ext_ref6 = fields.Char('Ext Ref6', size=16)
    description = fields.Char('Description', size=64)
    code = fields.Char('Code', help="Analysis code/ Tax line code!", size=16)
    short_name = fields.Char('Short Name', size=32)
    value = fields.Float('Value', help='Tax amount for this line!')
    doc_tax_turnover = fields.Float(string='Doc Tax Turnover')
    inv_id = fields.Many2one(
        'move.odooto.roularta',
        string='invoice_from_Reference',
        ondelete='cascade',
        required=True,
        copy=False
    )
    roularta_response = fields.Integer(
        'Roularta Response'
    )
    roularta_response_message = fields.Text(
        'Reply message'
    )

    def call_roularta(self, inv, xml=False):
        config = self.env['roularta.config'].search([], limit=1)
        url = str(config.host)
        user = str(config.username)
        pwd = str(config.password)

        trans_code = ''
        invoice = inv.invoice_id
        if invoice.type == 'out_invoice':
            trans_code = 'VFOO'
        elif invoice.type == 'out_refund':
            trans_code = 'VCOO'
        elif invoice.type == 'in_invoice':
            trans_code = 'IFOO'
        elif invoice.type == 'in_refund':
            trans_code = 'ICOO'

        transaction_lines = []
        for line in self.search([('id', 'in', self.ids)], order='number asc'):
            entry = OrderedDict([
                ('trans:Number', line.number),
                ('trans:DestCode', line.dest_code),
                ('trans:AccountCode', line.account_code),
                ('trans:DocValue', line.doc_value),
                ('trans:DualRate', line.dual_rate),
                ('trans:DocRate', line.doc_rate),
                ('trans:LineType', line.line_type),
                ('trans:LineSense', line.line_sense),
                ('trans:LineOrigin', line.line_origin),
                ('trans:DueDate', datetime.strptime(line.due_date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S')),
            ])

            if line.line_type == 'summary':
                entry.update(
                    OrderedDict([
                        ('trans:DocSumTax', line.doc_sum_tax),
                        ('trans:MediaCode', line.media_code),
                        ('trans:UserRef1', line.user_ref1 or ''),
                        ('trans:UserRef2', line.user_ref2 or ''),
                        ('trans:ExtRef1', line.ext_ref1 or ''),
                        ('trans:ExtRef2', line.ext_ref2 or ''),
                        ('trans:ExtRef6', line.ext_ref6 or ''),
                    ])
                )
            elif line.line_type == 'analysis':
                entry.update(
                    OrderedDict([
                        ('trans:TaxInclusive',False),
                        ('trans:ExtRef4',line.ext_ref4),
                        ('trans:Description',line.description),

                    ])
                )

                if line.code:
                    entry.update(
                        OrderedDict([
                            ('trans:Taxes', OrderedDict([
                                ('trans:Tax', OrderedDict([
                                    ('trans:Code', line.code),
                                    ('trans:ShortName', line.short_name),
                                    ('trans:Value', line.value)
                                ])
                                 )])
                             ),
                        ])
                    )

            elif line.line_type == 'tax':
                entry.update(
                    OrderedDict([
                        ('trans:TaxLineCode',line.code),
                        ('trans:DocTaxTurnover',line.doc_tax_turnover)
                    ])
                )

            transaction_lines.append(entry)

        xmlDt = OrderedDict([
            ('soapenv:Envelope', OrderedDict([
                ('@xmlns:soapenv', 'http://schemas.xmlsoap.org/soap/envelope/'),
                ('@xmlns:web', 'http://www.coda.com/efinance/schemas/inputext/input-14.0/webservice'),
                ('@xmlns:tran', 'http://www.coda.com/efinance/schemas/transaction'),
                ('@xmlns:flex', 'http://www.coda.com/common/schemas/flexifield'),
                ('@xmlns:att', 'http://www.coda.com/common/schemas/attachment'),
                ('@xmlns:inp', 'http://www.coda.com/efinance/schemas/inputext'),
                ('@xmlns:mat', 'http://www.coda.com/efinance/schemas/matching'),
                ('@xmlns:ass', 'http://www.coda.com/efinance/schemas/association'),
                ('soapenv:Header', OrderedDict([
                    ('web:Options', OrderedDict([
                        ('@user', config.username),
                        ('@company', inv.company_code)
                    ]))
                ])),
                ('soapenv:Body', OrderedDict([
                    ('web:PostOptions', OrderedDict([
                        ('@postto', "anywhere")
                    ])),
                    ('web:PostRequest', OrderedDict([
                        ('Transaction', OrderedDict([
                            ('trans:Header', OrderedDict([
                                ('@xmlns:trans', 'http://www.coda.com/efinance/schemas/transaction'),
                                ('trans:Key', OrderedDict([
                                    ('trans:CmpCode', inv.company_code),
                                    ('trans:Code', trans_code),
                                    ('trans:Number', inv.number)
                                ])),
                                ('trans:Period', inv.period),
                                ('trans:CurCode', inv.curcode.name),
                                ('trans:Date',
                                 datetime.strptime(inv.date, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S')),
                            ])),
                            ('trans:Lines', OrderedDict([
                                ('trans:Line', transaction_lines),
                                ('@xmlns:trans', 'http://www.coda.com/efinance/schemas/transaction'),
                                ])
                            ),
                        ]))
                    ])),

                ])),

            ]))
        ])

        xmlData = xmltodict.unparse(xmlDt, pretty=True, full_document=False)

        headers = {
            'SOAPAction': 'uri-coda-webservice/14.000.0030/finance/Input/Post',
            'Content-Type': 'application/xml',
        }

        try:
            response = requests.request("POST", url, headers=headers, data=str(xmlData), auth=HTTPBasicAuth(user, pwd))

            self.write({
                'roularta_response': response.status_code,
                'roularta_response_message': response.text,
            })
            inv.write({'xml_message': str(xmlData)})
        except Exception as e:
            raise FailedJobError(
                _('Error Roularta Interface call: %s') % (e))
        return response



