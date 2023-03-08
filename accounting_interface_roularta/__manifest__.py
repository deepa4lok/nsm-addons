# -*- coding: utf-8 -*-
{
    'name': "accounting_interface_roularta",

    'summary': """
        This module provides a accounting interface between Odoo and the Roularta systems. """,

    'description': """
        This module provides a accounting interface between Odoo and the Roularta systems. 
    """,

    'author': "K.Sushma",
    'website': "http://www.tosc.nl",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/10.0/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'integration',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['account', 'sale_advertising_order',
                'account_invoice_2step_validation'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/roularta_security.xml',
        'views/roularta_config_view.xml',
        'views/account_view.xml',
        'views/sale_advertising_view.xml',
    ],
    'external_dependencies': {
        'python': ['xmltodict','requests'],
    },
    # only loaded in demonstration mode
    'demo': [
        # 'demo/demo.xml',
    ],
}