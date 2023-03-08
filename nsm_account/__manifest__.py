# -*- encoding: utf-8 -*-
##############################################################################
#
# Copyright (c) 2013 Megis - Willem Hulshof - www.megis.nl
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs.
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company like Veritos.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
##############################################################################

{
    'name' : 'nsm_account',
    'version' : '1.0',
    'category': 'other',
    'description': """
Enchances the Accounting Module according to NSM Requirements
=============================================================================
* adds "section_id" and "department_id" to analytic account
* limits analytic_lines tree to section_id.user_id.
* adds "publishing date" to analytic account.
* adds Custom Invoice Layout
* Merge To Print Supplier Invoices


    """,
    'author'  : 'Magnus - Willem Hulshof',
    'website' : 'http://www.magnus.nl',
    'depends' : ['account', 'analytic', 'hr', 'crm',
                'account_invoice_2step_validation',
                'publishing_accounts',
                'account_invoice_supplier_ref_unique',
                'operating_unit_report_layout', 'sale',
                'sale_advertising_operating_unit',
                'account_operating_unit',
                'publishing_invoicing'
    ],
    'data' : [
	          "security/analytic_security_view.xml",
              "data/account_data.xml",

              'wizard/supplier_merge_pdf_view.xml',

              'report/report_blank_invoice.xml',

              "views/report.xml",
              "report/report_invoice.xml",
              "views/res_partner_view.xml",
              "views/res_company_view.xml",
              "views/account_view.xml",
              "views/account_invoice_view.xml",
              "views/sale_view.xml",
    ],
    'demo' : [],
    'installable': True
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

