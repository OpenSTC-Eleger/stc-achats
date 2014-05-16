# -*- coding: utf-8 -*-

##############################################################################
#    Copyright (C) 2012 SICLIC http://siclic.fr
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
#############################################################################

from osv import osv, fields
from datetime import datetime
import re
import unicodedata
import netsvc
import decimal_precision as dp
from tools.translate import _
from openbase.openbase_core import OpenbaseCore

class crossovered_budget(OpenbaseCore):
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
        'code_budget_ciril':fields.char('CIRIL Budget Code', size=16),
        'service_id':fields.many2one('openstc.service','Service',required=True),
        }
    
    _defaults = {
        'code_budget_ciril':lambda *a: '0',
        }
crossovered_budget()

class crossovered_budget_lines(OpenbaseCore):
    _rec_name = "name"
    
    def name_get(self, cr, uid, ids, context=None):
        ret = []
        for budget in self.browse(cr, uid, ids, context=context):
            budget.name
            val = _(u'%s / %s : %s € (%.2f %% consummed)') %(budget.crossovered_budget_id.name, budget.analytic_account_id.name_get()[0][1],budget.planned_amount - budget.openstc_practical_amount, budget.openstc_erosion)
            ret.append((budget.id,val))
        return ret
    
    def name_search(self, cr, uid, name='', args=[], operator='ilike', context={}, limit=80):
        #ids = self.search(cr, uid, [('analytic_account_id.complete_name',operator,name)] + args, limit=limit, context=context)
        ids = self.search(cr, uid, ['|',('analytic_account_id.name',operator,name),('crossovered_budget_id.name',operator,name)] + args, limit=limit, context=context)
#        if not ids:
#            ids = self.search(cr, uid, [('analytic_account_id.service_id.code',operator,name)] + args, limit=limit, context=context)
        return self.name_get(cr, uid, ids, context=context)
    
    #custom field for public account : returns amount with taxes included
    def _openstc_pract(self, cr, uid, ids, name, args, context=None):
        #first, we get engage_lines that matches dates and current budget line analytic account
        ret = {}.fromkeys(ids,{'openstc_practical_amount':0.0, 'openstc_erosion':0.0})
        engage_obj = self.pool.get("open.engagement.line")
        
        cr.execute(''' select budget.id as id, budget.planned_amount, sum(line.amount) as amount
        from open_engagement_line as line, crossovered_budget_lines as budget
        where budget.id = line.budget_line_id
        and line.budget_line_id in {budget_line_ids}
        group by budget.planned_amount, budget.id'''.format(budget_line_ids=tuple(ids)))
        amount = 0.0
        data = cr.fetchall()
        for d in data:
            erosion = 0.0
            if d[1]:
                erosion = d[2] * 100.0 / d[1]
            ret[d[0]] = {'openstc_practical_amount':d[2],
                                 'openstc_erosion':erosion}
        
        return ret
    
    _inherit = "crossovered.budget.lines"
    _columns = {
            'openstc_practical_amount':fields.function(_openstc_pract, multi="openstc_pract_amount", method=True, string="Montant Consommé", type="float", digits_compute=dp.get_precision('Account')),
            'openstc_erosion':fields.function(_openstc_pract, multi="openstc_pract_amount", method=True, string="Taux d'érosion (%)", type="float", digits_compute=dp.get_precision('Account')),
            'openstc_general_account':fields.many2one('account.account', 'M14 account', help="M14 account corresponding to this budget line"),
            'openstc_code_antenne':fields.char('Antenne Code', size=16, help='Antenne code from CIRIL instance'),
            'name':fields.related('analytic_account_id','complete_name',string='Budget name',type='char',store=True),
        }
    
    

    
    def onchange_openstc_general_account(self, cr, uid, ids, openstc_general_account=False):
        if openstc_general_account:
            #we create an account.budget.post to respect base work of budget, even if we don't use it anymore
            account = self.pool.get("account.account").browse(cr, uid, openstc_general_account)
            post = self.pool.get("account.budget.post").search(cr, uid, [('account_ids','=',openstc_general_account)])
            if post:
                post = post[0]
            else:
                post = self.pool.get("account.budget.post").create(cr, uid, {'code':account.code,
                                                                    'name':account.name,
                                                                    'account_ids':[(6,0,[account.id])]})
            
        return {'value':{'general_budget_id':post}}
        
crossovered_budget_lines()

    