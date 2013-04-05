# -*- coding: utf-8 -*-

##############################################################################
#
#    Open Achat Stocks module for OpenERP, module Open Achat Stocks
#    Copyright (C) 200X Company (<http://website>) bp
#
#    This file is a part of Open Achat Stocks
#
#    Open Achat Stocks is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Open Achat Stocks is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from osv import osv, fields
from datetime import datetime
import re
import unicodedata
import netsvc
import decimal_precision as dp

class crossovered_budget(osv.osv):
    _inherit = "crossovered.budget"
    _name = "crossovered.budget"
    
    def _calc_amounts(self, cr, uid, ids,  field_name, args, context=None):
        res = {}
        for budget in self.browse(cr, uid, ids, context):
            pract = 0.0
            theo = 0.0
            planned = 0.0
            openstc_practical = 0.0
            #Pour chaque budget, on ajoute les montants de toutes leurs lignes budgétaires
            for line in budget.crossovered_budget_line:
                pract += line.practical_amount
                theo += line.theoritical_amount
                planned += line.planned_amount
                openstc_practical += line.openstc_practical_amount
            res.update({budget.id:{'pract_amount':pract, 'theo_amount':theo, 'planned_amount':planned, 'openstc_practical_amount':openstc_practical}})
        return res
    
    _columns = {
        'planned_amount':fields.function(_calc_amounts, method=True, multi = True, string="Montant Plannifié", type='float'),
        'pract_amount':fields.function(_calc_amounts, method=True, multi = True, string="Montant Pratique", type='float'),
        'theo_amount':fields.function(_calc_amounts, method=True, multi = True, string="Montant Théorique", type='float'),
        'openstc_practical_amount':fields.function(_calc_amounts, method=True, multi = True, string="Montant Consommé", type='float'),
        }
    
crossovered_budget()

class crossovered_budget_lines(osv.osv):
    
    #custom field for public account : returns amount with taxes included
    def _openstc_pract(self, cr, uid, ids, name, args, context=None):
        #first, we get engage_lines that matches dates and current budget line analytic account
        ret = {}
        for line in self.browse(cr, uid, ids, context):
            engage_line_ids = self.pool.get("open.engagement.line").search(cr, uid, [('account_analytic_id','=',line.analytic_account_id.id),
                                                                                     ('engage_id.date_engage_validated','<=', line.date_to),
                                                                                     ('engage_id.date_engage_validated','>=',line.date_from),
                                                                                     ('engage_id.state','not in',('draft','to_validate','check_except'))])
            amount = 0.0
            #next, if we found engage_lines, we compute with them, 
            #else, we use default openerp practical amount (for example to display sales amount which doesn't work with engages)
            if engage_line_ids:
                for engage_line in self.pool.get("open.engagement.line").browse(cr, uid, engage_line_ids, context):
                    amount += engage_line.amount
            else:
                amount = line.practical_amount
            ret[line.id] = amount
        return ret
    
    def _openstc_erosion(self, cr, uid, ids, name, args, context=None):
        ret = {}
        for line in self.browse(cr, uid, ids, context):
            ret[line.id] = line.openstc_practical_amount * 100.0 / line.planned_amount
        return ret
    
    _inherit = "crossovered.budget.lines"
    _columns = {
            'openstc_practical_amount':fields.function(_openstc_pract, method=True, string="Montant Consommé", type="float", digits_compute=dp.get_precision('Account')),
            'openstc_erosion':fields.function(_openstc_erosion, method=True, string="Taux d'érosion (%)", type="float", digits=(3,2)),
            'openstc_general_account':fields.many2one('account.account', 'M14 account', help="M14 account corresponding to this budget line"),
        }
    
    def onchange_openstc_general_account(self, cr, uid, ids, openstc_general_account=False,context=None):
        if openstc_general_account:
            #we create an account.budget.post to respect base work of budget, even if we don't use it anymore
            account = self.pool.get("account.account").browse(cr, uid, openstc_general_account,context=context)
            post = self.pool.get("account.budget.post").search(cr, uid, [('account_ids','=',openstc_general_account)],context=context)
            if not post:
                post = self.pool.get("account.budget.post").create({'code':account.code,
                                                                    'name':account.name,
                                                                    'account_ids':[(6,0,[account.id])]}, 
                                                                   context=context)
            
        return {'value':{'general_budget_id':post}}
        
crossovered_budget_lines()

    