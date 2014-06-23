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
from datetime import timedelta
import re
import unicodedata
import netsvc
import decimal_precision as dp
from tools.translate import _
from openbase.openbase_core import OpenbaseCore

class crossovered_budget(OpenbaseCore):
    _inherit = "crossovered.budget"
    _name = "crossovered.budget"
    
    """for performance purpose, filter fields to fetch from crossovered.budget.lines, 2 couples are available : 
        - 'planned_amount' and 'openstc_practical_amount' (our use, fast to compute)
        - 'pract_amount' and 'theo_amount' (openerp old use, very slow to compute)
        @return: dict with {id: values} where values is a dict containing values of each 'field_name'"""
    def _calc_amounts(self, cr, uid, ids,  field_name, args, context=None):
        res = {}       
        map_line_fields = {'planned_amount':'planned_amount',
                          'openstc_practical_amount': 'openstc_practical_amount',
                          'pract_amount': 'practical_amount',
                          'theo_amount': 'theoritical_amount'}
        line_fields = [map_line_fields.get(x) for x in field_name if x in map_line_fields.keys()]

        budget_line_obj = self.pool.get('crossovered.budget.lines')
        for budget in self.read(cr, uid, ids, ['crossovered_budget_line'], context=context):
            pract = 0.0
            theo = 0.0
            planned = 0.0
            openstc_practical = 0.0
            #Pour chaque budget, on ajoute les montants de toutes leurs lignes budgétaires
            for line in budget_line_obj.read(cr, uid, budget['crossovered_budget_line'], line_fields, context=context):
                pract += line.get('practical_amount', 0.0)
                theo += line.get('theoritical_amount', 0.0)
                planned += line.get('planned_amount', 0.0)
                openstc_practical += line.get('openstc_practical_amount', 0.0)
            res.update({budget['id']:{'pract_amount':pract, 'theo_amount':theo, 'planned_amount':planned, 'openstc_practical_amount':openstc_practical}})
        return res
    
    def _search_openstc_practical_amount(self, cr, uid, obj, name, args):
        
        return
    
    _actions = {
        'validate': lambda self, cr, uid, record, groups_code: record.state == 'confirm',
        'confirm': lambda self, cr, uid, record, groups_code: record.state == 'draft',
        'cancel': lambda self, cr, uid, record, groups_code: record.state in ('confirm',),
        'done': lambda self, cr, uid, record, groups_code: record.state == 'validate',
        'renew': lambda self, cr, uid, record, groups_code: record.state == 'validate',
        'delete': lambda self, cr, uid, record, groups_code: record.state == 'confirm',
        }
    
    def _get_budget_by_line_ids(self, cr, uid, ids, context=None):
        return self.search(cr, uid, [('crossovered_budget_line.id', 'in', ids)], context=context)
    
    store_values = {'crossovered.budget': [lambda self,cr,uid,ids,ctx={}:ids, [], 11],
                'crossovered.budget.lines':[_get_budget_by_line_ids, [], 10]}
    
    _columns = {
        'planned_amount':fields.function(_calc_amounts, method=True, multi = 'openstc_budget_amount', string="Montant Plannifié", type='float', store=store_values),
        'pract_amount':fields.function(_calc_amounts, method=True, multi = 'old_budget_amount', string="Montant Pratique", type='float', store=store_values),
        'theo_amount':fields.function(_calc_amounts, method=True, multi = 'old_budget_amount', string="Montant Théorique", type='float', store=store_values),
        'openstc_practical_amount':fields.function(_calc_amounts, fnct_search=_search_openstc_practical_amount, method=True, multi = 'openstc_budget_amount', string="Montant Consommé", type='float', store=store_values),
        'code_budget_ciril':fields.char('CIRIL Budget Code', size=16),
        'service_id':fields.many2one('openstc.service','Service',required=True),
        
        'validate_note': fields.text('Validate note'),
        'done_note': fields.text('Validate note'),
        'cancel_note': fields.text('Validate note'),
        
        'new_name': fields.char('New name', size=128),
        'new_date_from': fields.date('New Date from'),
        'new_date_to': fields.date('New Date to'),
        'new_service_id': fields.many2one('openstc.service', 'service for renewed budget'),
        'renewed_budget_id': fields.many2one('crossovered.budget', 'New budget created from renew'),
        }
    
    def prepare_default_values_renewed_contract(self, cr, uid, record, context=None):
        return {
            'service_id':record.new_service_id.id if record.new_service_id else record.service_id.id,
            'date_from': record.new_date_from or record.date_from,
            'date_to': record.new_date_to or record.date_to,
            'name': record.new_name or record.name
            }
    
    def renew(self, cr, uid, ids, context=None):
        ret = []
        for budget in self.browse(cr, uid, ids):
            val = self.prepare_default_values_renewed_contract(cr, uid, budget, context=context)
            new_id = self.copy(cr, uid, budget.id, val, context=context)
            ret.append(new_id)
        return ret
    
    def budget_renew(self, cr, uid, ids):
        self.renew(cr, uid, ids)
    
    def update_renew_budget_values(self, cr, uid, ids, context=None):
        for budget in self.browse(cr, uid, ids, context=context):
            delta = timedelta(365)
            date_start = datetime.strptime(budget.date_from, '%Y-%m-%d')
            date_start = date_start + delta
            date_end = datetime.strptime(budget.date_to, '%Y-%m-%d')
            date_end = date_end + delta
            budget.write({'new_service_id': budget.service_id.id,
                          'new_date_from': date_start.strftime('%Y-%m-%d'),
                          'new_date_to':date_end.strftime('%Y-%m-%d'),
                          'new_name':budget.name}, context=context)
        return True
    
    def budget_validate(self, cr, uid, ids):
        self.update_renew_budget_values(cr, uid, ids)
        super(crossovered_budget,self).budget_validate(cr, uid, ids)
        return True
    
    def write(self, cr, uid, ids, vals, context=None):
        signal = False
        if 'wkf_evolve' in vals:
            signal = vals.pop('wkf_evolve')
        ret = super(crossovered_budget, self).write(cr, uid, ids, vals, context=context)
        if signal:
            wkf_service = netsvc.LocalService('workflow')
            for id in ids:
                wkf_service.trg_validate(uid, self._name, id, signal, cr)
        return ret
    
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
    
    def _get_complete_name(self, cr, uid, ids, name ,args, context=None):
        ret = {}.fromkeys(ids, '')
        for budget_line in self.browse(cr, uid, ids, context=context):
            ret[budget_line.id] = budget_line.name_get()[0][1]
        return ret
    
    #custom field for public account : returns amount with taxes included
    def _openstc_pract(self, cr, uid, ids, name, args, context=None):
        #first, we get engage_lines that matches dates and current budget line analytic account
        ret = {}.fromkeys(ids,{'openstc_practical_amount':0.0, 'openstc_erosion':0.0})
        engage_obj = self.pool.get("open.engagement.line")
        
        cr.execute(''' select budget.id as id, budget.planned_amount, sum(line.amount) as amount
        from open_engagement_line as line, crossovered_budget_lines as budget
        where budget.id = line.budget_line_id
        and line.budget_line_id in %s
        group by budget.planned_amount, budget.id''', (tuple(ids),))
        amount = 0.0
        data = cr.fetchall()
        for d in data:
            erosion = 0.0
            if d[1]:
                erosion = d[2] * 100.0 / d[1]
            ret[d[0]] = {'openstc_practical_amount':d[2],
                                 'openstc_erosion':erosion}
        
        return ret
    
    def _get_budget_by_line_ids(self, cr, uid, ids, context=None):
        cr.execute('''select id 
        from crossovered_budget_lines as budget, open_engagement_line as engage 
        where budget.id = engage.budget_line_id 
        and engage.id in %s''', (tuple(ids),))
        return [x[0] for x in cr.fetchall()]
    
    store_values = {'crossovered.budget.lines': [lambda self,cr,uid,ids,ctx={}:ids, [], 11],
                    'open.engagement.line':[_get_budget_by_line_ids, [], 10]}
    
    _inherit = "crossovered.budget.lines"
    _columns = {
            'openstc_practical_amount':fields.function(_openstc_pract, multi="openstc_pract_amount", method=True, string="Montant Consommé", type="float", digits_compute=dp.get_precision('Account'), store=store_values),
            'openstc_erosion':fields.function(_openstc_pract, multi="openstc_pract_amount", method=True, string="Taux d'érosion (%)", type="float", digits_compute=dp.get_precision('Account'), store=store_values),
            'openstc_general_account':fields.many2one('account.account', 'M14 account', help="M14 account corresponding to this budget line"),
            'openstc_code_antenne':fields.char('Antenne Code', size=16, help='Antenne code from CIRIL instance'),
            'name':fields.related('analytic_account_id','complete_name',string='Budget name',type='char',store=True),
            'complete_name': fields.function(_get_complete_name, method=True, string="Complete name", type='char', store=True),
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
    
    def create(self, cr, uid, vals, context=None):
        final_vals = {}
        #create default budget.post account
        account_id = vals.get('openstc_general_account',False)
        if account_id and not 'general_budget_id' in vals:
            values = self.onchange_openstc_general_account(cr, uid, False, openstc_general_account=account_id)
            vals.update(values['value'])
        #check if dates are in vals (else put default values)
        if 'date_from' not in vals or 'date_to' not in vals:
            budget = self.pool.get('crossovered.budget').read(cr, uid, vals.get('crossovered_budget_id'), ['date_from','date_to'], context=context)
            final_vals.update({'date_from': budget.get('date_from'), 'date_to':budget.get('date_to')})
        #finally, merge default values with input ones
        final_vals.update(vals)
        ret = super(crossovered_budget_lines, self).create(cr, uid, final_vals, context=context)
        return ret
    
crossovered_budget_lines()

    