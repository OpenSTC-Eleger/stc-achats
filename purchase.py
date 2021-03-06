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
from tools import config
from datetime import datetime
import re
import netsvc
import unicodedata
import time
import base64
from tools.translate import _
from ciril_template_files import template_ciril_txt_file_engagement
import urllib2
import os
from urllib2 import URLError
import shutil
from openbase.openbase_core import OpenbaseCore

class purchase_order_line(OpenbaseCore):
    _inherit = "purchase.order.line"
    _name = "purchase.order.line"

    
    def _get_budget_dispo(self, cr, uid, ids, name ,args, context=None):
        ret = {}.fromkeys(ids, 0.0)
        for line in self.browse(cr, uid, ids, context):
            #we compute only for draft purchases 
            if not line.order_id or line.order_id.state == 'draft':
                #line_id = self.pool.get("crossovered.budget.lines").search(cr, uid, [('analytic_account_id','=',line.account_analytic_id.id)])
                line_id = line.budget_line_id
                if line_id:
                    #return {'warning':{'title':'Erreur','message':'Ce compte Analytique n appartient a aucune ligne budgetaire'}}
                    #if isinstance(line_id, list):
                        #line_id = line_id[0]
                    #budget_line = self.pool.get("crossovered.budget.lines").browse(cr, uid, line_id)
                    res = abs(line_id.planned_amount) - abs(line_id.openstc_practical_amount)
                    ret[line.id] = res
        return ret
    
    def _get_amount_ttc(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, 0.0)
        for line in self.browse(cr, uid, ids, context):
            amount_line = line.price_subtotal
            for c in self.pool.get('account.tax').compute_all(cr, uid, line.taxes_id, line.price_unit, line.product_qty, line.order_id.partner_address_id.id, line.product_id.id, line.order_id.partner_id)['taxes']:
                    amount_line += c.get('amount', 0.0)
            ret[line.id] = amount_line
        return ret
    
    #return all lines concerned by the same purchase order and the same account analytic line
    def _get_line_dispo(self, cr, uid, ids, name, args, context=None):
        #dict of dict : {po_id:{account_id1:[line1,line2], account_id2:[line1,line2,line3]}}
        grouped_lines = {}
        for line in self.browse(cr, uid, ids, context):
            grouped_lines.setdefault(line.order_id.id,{})
            grouped_lines[line.order_id.id].setdefault(line.budget_line_id.id, [])
            grouped_lines[line.order_id.id][line.budget_line_id.id].append(line)
        
        line_ok = []
        line_not_ok = []
        ret = {}
        for order_id, values in grouped_lines.items():
            for budget_id, lines in values.items():
                restant = lines[0].budget_dispo
                for line in lines:
                    restant -= line.amount_ttc
                if restant > 0.0:
                    ret.update({}.fromkeys([x.id for x in lines],True))
                else:
                    ret.update({}.fromkeys([x.id for x in lines],False))
        
        return ret
    
    _columns = {
        #'budget_dispo':fields.float('Budget Disponible', digits=(6,2)),
        'budget_dispo':fields.function(_get_budget_dispo, method=True, type="float", string="Budget Disponible"),
        'tx_erosion': fields.float('Taux Erosion de votre Service', digits=(2,2)),
        'budget_dispo_info':fields.related('budget_dispo', type="float", string='Budget Disponible (Euros)', digits=(6,2), readonly=True),
        'tx_erosion_info': fields.related('tx_erosion', string='Taux Erosion de votre Service (%)', type="float", digits=(2,2), readonly=True),
        #'dispo':fields.boolean('Budget OK',readonly=True),
        'dispo':fields.function(_get_line_dispo, string='Budget OK', method=True, type='boolean'),
        'amount_ttc':fields.function(_get_amount_ttc, method=True, string="Montant", type="float", store={'purchase.order.line':[lambda self,cr,uid,ids,ctx:ids,['product_qty','price_unit','taxes_id'],10]}),
        'merge_line_ids':fields.one2many('openstc.merge.line.ask','po_line_id','Ventilation des Besoins'),
        'in_stock':fields.float('Qté qui sera Stockée', digits=(3,2)),
        'in_stock_info':fields.related('in_stock',type='float', digits=(3,2), string='Qté qui sera Stockée', readonly=True),
        'engage_line_id':fields.many2one('open.engagement.line', 'Numéro d\'Engagement'),
        'budget_line_id':fields.many2one('crossovered.budget.lines','Budget line'),
        }
    
    
    _defaults = {
        'dispo': False,
        'date_planned': fields.date.context_today,
        }
    
    def _check_qte_merge_qte_po(self, cr, uid, ids, context=None):
        for line in self.browse(cr, uid, ids, context):
            qte_ref = line.product_qty
            qte = 0
            for merge_line in line.merge_line_ids:
                #Dans le cas où le produit n'est pas encore renseigné (création via bon de commande, il sera associé automatiquement avec celui de la ligne en cours
                if not merge_line.product_id or merge_line.product_id.id == line.product_id.id:
                    qte += merge_line.qty_remaining
                else:
                    raise osv.except_osv(_('Error'),_('you associated merge lines that does not math the product of this order line'))
            return qte_ref >= qte
        return False
    
    _constraints = [(_check_qte_merge_qte_po,_('Error, product qty is lower than summed merge lines product qty'),['product_id','merge_line_ids'])]
    
    def onchange_budget_line_id(self, cr, uid, ids, budget_line_id=False):
        if budget_line_id:
            line = self.pool.get('crossovered.budget.lines').browse(cr, uid, budget_line_id)
            avail = abs(line.planned_amount) - abs(line.openstc_practical_amount)
            return {'value':{'account_analytic_id':line.analytic_account_id.id, 'budget_dispo_info':avail,'budget_dispo':avail,'tx_erosion':line.openstc_erosion,'tx_erosion_info':line.openstc_erosion}}
        return {'value':{'account_analytic_id':False, 'budget_dispo_info':0.0,'budget_dispo':0.0,'tx_erosion':0.0,'tx_erosion_info':0.0}}
    
    #deprecated: use onchange_budget_line_id instead of this one
    def onchange_account_analytic_id(self, cr, uid, ids, account_analytic_id=False):
        #On récupère la ligne budgétaire en rapport a ce compte analytique 
        if account_analytic_id:
            line_id = self.pool.get("crossovered.budget.lines").search(cr, uid, [('analytic_account_id','=',account_analytic_id)])
            if not line_id:
                return {'warning':{'title':'Error','message':_('this analytic account has not any budget line associated')}}
            if isinstance(line_id, list):
                line_id = line_id[0]
                #print("Warning, un meme compte analytique est present dans plusieurs lignes de budgets")
            line = self.pool.get("crossovered.budget.lines").browse(cr, uid, line_id)
            res = abs(line.planned_amount) - abs(line.openstc_practical_amount)
            res_erosion = abs(line.openstc_practical_amount) / abs(line.planned_amount) * 100
            #TODO: Intégrer le taux d'érosion d'un service
            return {'value':{'budget_dispo_info':res,'budget_dispo':res,'tx_erosion':res_erosion,'tx_erosion_info':res_erosion}}
        return {'value':{'budget_dispo_info':0.0,'budget_dispo':0.0,'tx_erosion':0.0,'tx_erosion_info':0.0}}
    
    #override to add merge_line asks and to include account.analytic.default (base OpenERP module)
    def onchange_product_id(self, cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order=False, fiscal_position_id=False, date_planned=False,
            name=False, price_unit=False, notes=False, context=None, account_analytic_id=False):
        
        #1- adding merge_asks
        merge_action = []
        for pol in self.browse(cr, uid, ids ,context):
            merge_action.extend([(1,x.id, {'product_id':product_id}) for x in pol.merge_line_ids])
            
        ret = super(purchase_order_line, self).onchange_product_id(cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order, fiscal_position_id, date_planned,
            name, price_unit, notes, context)
        ret['value'].update({'merge_line_ids':merge_action})

        return ret
    
    def onchange_merge_line_ids(self, cr, uid, ids, merge_line_ids=False, product_qty=False, context=None):
        if product_qty:
            qte_restante = product_qty
            for action in merge_line_ids:
                if action[0] == 1 or action[0] == 0:
                    qte_restante -= action[2]['product_qty']
                elif action[0] == 4:
                    qte_restante -= self.pool.get("openstc.merge.line.ask").read(cr, uid, action[1], ['product_qty'],context=context)['product_qty']
        ret = {'value':{'in_stock':qte_restante,'in_stock_info':qte_restante}}
        if qte_restante < 0:
            ret.update({'warning':{'title':_('Warning'),'message':_('merge lines qty that you have planned is greater than product qty to purchase.')}})
        return ret
    
    def create(self, cr, uid, vals, context=None):
        #Lors de l'ajout de merge.lines.ask, le logiciel force la donnée product_id de celui-ci
        line_id = super(purchase_order_line, self).create(cr, uid, vals, context)
        line = self.browse(cr, uid, line_id, context)
        merge_action = []
        merge_action.extend([(1,merge_line.id,{'product_id':line.product_id.id})for merge_line in line.merge_line_ids])
        super(purchase_order_line, self).write(cr, uid, line.id, {'merge_line_ids':merge_action})
        #On force le user à revalider le budget
        self.pool.get("purchase.order").write(cr, uid, line.order_id.id, {'validation':'budget_to_check'})
        return line_id
    
    def write(self, cr, uid, ids, vals, context=None):
        budget_to_check = False
        if 'product_id' in vals or 'price_unit' in vals or 'product_qty' in vals:
            vals.update({'dispo':False})
            budget_to_check = True
        super(purchase_order_line, self).write(cr, uid, ids, vals, context)
        for line in self.browse(cr, uid, ids, context):
            merge_action = []
            merge_action.extend([(1,merge_line.id,{'product_id':line.product_id.id})for merge_line in line.merge_line_ids if not merge_line.product_id])
            super(purchase_order_line, self).write(cr, uid, line.id, {'merge_line_ids':merge_action})
        return True
    
purchase_order_line()

#Surcharge de purchase.order pour ajouter les étapes de validation pour collectivités : 
#Vérif dispo budget, sinon blocage
#Vérif validation achat par DST + Elu si > 300 euros (EDIT: voir modifs ALAMICHEL dans son mail)
class purchase_order(OpenbaseCore):
    
    """ @note: Remove all char that is not a simple ascii letter"""
    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')
    
    """@note: Remove all char that is an accent (category 'Mn' according to unicode RFC 5.2 used by python) """
    def to_upper_unaccent(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x) <> 'Mn').upper()
    
    def _custom_sequence(self, cr, uid, context):
        seq = self.pool.get("ir.sequence").next_by_code(cr, uid, 'openstc.purchase.order',context)
        user = self.pool.get("res.users").browse(cr, uid, uid)
        prog = re.compile('[Oo]pen[a-zA-Z]{3}/[Mm]anager')
        service = None
        if 'service_id' in context:
            service = context['service_id']
            service = self.pool.get("openstc.service").browse(cr, uid, service)

#        for group in user.groups_id:
#            if prog.search(group.name):
#                if isinstance(user.service_ids, list) and not service:
#                    service = user.service_ids[0]
        if service:
            seq = seq.replace('xxx',self.remove_accents(service.name[:3]).upper())
        return seq
    
    def _create_report_attach(self, cr, uid, record, context=None):
        #sources inspired by _edi_generate_report_attachment of EDIMIXIN module
        ir_actions_report = self.pool.get('ir.actions.report.xml')
        matching_reports = ir_actions_report.search(cr, uid, [('model','=',self._name),
                                                              ('report_type','=','pdf',),
                                                               ('report_name','=','purchase.order')])
        ret = False
        if matching_reports:
            report = ir_actions_report.browse(cr, uid, matching_reports[0])
            report_service = 'report.' + report.report_name
            service = netsvc.LocalService(report_service)
            try:
                (result, format) = service.create(cr, uid, [record.id], {'model': self._name}, context=context)
                eval_context = {'time': time, 'object': record}
                if not report.attachment or not eval(report.attachment, eval_context):
                    # no auto-saving of report as attachment, need to do it manually
                    result = base64.b64encode(result)
                    file_name = record.name_get()[0][1]
                    file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', file_name)
                    file_name += ".pdf"
                    ir_attachment = self.pool.get('ir.attachment').create(cr, uid, 
                                                                          {'name': file_name,
                                                                           'datas': result,
                                                                           'datas_fname': file_name,
                                                                           'res_model': self._name,
                                                                           'res_id': record.id},
                                                                          context=context)
                    ret = ir_attachment
            except:
                pass
            
        return ret
    
    AVAILABLE_ETAPE_VALIDATION = [('budget_to_check','Budget to Check'),('engagement_to_check','Purchase to Check'),
                                  ('done','Purchase validated'),('purchase_engaged','Purchase engaged'), ('purchase_paid','Purchase Paid')]
    _inherit = 'purchase.order'
    _name = 'purchase.order'
    
    def _get_need_confirm(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, True)
        for po in self.browse(cr, uid, ids, context=context):
            service = po.user_id and po.user_id.service_id
            if service:
                if service.has_purchase_validation:
                    ret[po.id] = service.purchase_max_amount_no_market <= po.amount_total
                else:
                    ret[po.id] = False
                
        return ret
    
    def _get_ids_from_users(self, cr, uid, ids, context=None):
        po_ids = self.search(cr, uid, [('user_id','in',ids)], context=None)
        return po_ids
    
    def _get_ids_from_pol(self,cr,uid,ids,context=None):
        po_ids = self.search(cr, uid, [('order_line','in',ids)])
        return po_ids
    
    def _get_all_budget_dispo(self, cr, uid, ids, name, args, context={}):
        ret = {}
        for po in self.browse(cr, uid, ids, context=context):
            ret[po.id] = True
            for line in po.order_line:
                if not line.dispo:
                    ret[po.id] = False
        return ret
    
    def _get_engage_attaches(self, cr, uid, ids, field_name, arg=None, context=None):

        po_ids = ids
        cr.execute('''select a.id, a.res_id, a.state, a.engage_done, a.datas_fname
                    from ir_attachment as a 
                    where a.res_id in %s and a.res_model = %s
                    group by a.res_id, a.id
                    order by a.create_date DESC''',(tuple(ids), self._name))
        ret = {}
        search_ids = []
        search_ids.extend(ids)
        for id in ids:
            ret.setdefault(id, {'attach_ids':[],'engage_to_treat':False,'all_invoices_treated':False, 
                                'attach_not_invoices': [], 'attach_waiting_invoice_ids': [], 'attach_invoices': []})
        for r in cr.fetchall():
            if r[1] in ids:
                attach_value = {'id': r[0], 'name': r[4]}
                #if attach is an invoice
                if r[2] <> 'not_invoice':
                    ret[r[1]]['attach_invoices'].append(attach_value)
                    #if an invoice has to be check, purchase will appear in board
                    if r[2] in ('to_check','except_send_mail') and not r[3]:
                        ret[r[1]]['engage_to_treat'] = True
                        ret[r[1]]['attach_waiting_invoice_ids'].append(r[0])
                        
                    ret[r[1]]['all_invoices_treated'] = len(ret[r[1]]['attach_waiting_invoice_ids']) == 0
                #else, if attach is not an invoice, add it to the not_invoice_ids
                else:
                    ret[r[1]]['attach_not_invoices'].append(attach_value)
                #for backward_compatibility only
                ret[r[1]]['attach_ids'].append(r[0])
            
                
        return ret
    
    def _search_engage_to_treat(self, cr, uid, obj, name, args, context={}):
        if not args:
            return []
        val = True
        for arg in args:
            if arg[1] == '=' and arg[2] is False:
                val = False
        cr.execute("select res_id from ir_attachment where state in ('to_check','except_send_mail') and res_model = %s and engage_done=False group by res_id;",(self._name,))
        return [('id','in' if val else 'not in',[x for x in cr.fetchall()])]
    
    def search_all_invoices_treated(self, cr, uid, obj, name, args, context={}):
        if not args:
            return []
        if ('all_invoices_treated','=',True) in args:
            cr.execute("select res_id from ir_attachment where state not in ('to_check','not_invoice') and res_model = %s and engage_done = False group by res_id;",(self._name,))
            return [('id','in',[x for x in cr.fetchall()])]
        return []
    
    def button_dummy(self, cr, uid, ids, context={}):
        display = False
        if context:
            display = 'display_popup' in context
        for po in self.browse(cr, uid, ids, context=context):
            for line in po.order_line:
                if not line.budget_line_id and display:
                    raise osv.except_osv(_('Error'),_('There is missing budget attributions in order lines'))
        return {'type':'ir.actions.act_window.close'}
    
    def _get_validation_order_items(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, {})
        for po in self.browse(cr, uid, ids, context=context):
            vals = {'waiting':[], 'confirm':[], 'refuse':[]}
            if po.validation_order_id:
                vals.update({'waiting': [{'validator':item.user_id and item.user_id.name or '',
                                'role': item.name} for item in po.validation_order_id.waiting_validation_item_ids]})
                confirms = []
                refuses = []
                for log in po.validation_order_id.validation_log_ids:
                    if log.state == 'confirm':
                        confirms.append({'validator':log.user_id.name,
                                        'role': log.validation_item_id.name,
                                        'date': log.date,
                                        'note': log.note})
                    else:
                        refuses.append({'validator':log.user_id.name,
                                        'role': log.validation_item_id.name,
                                        'date': log.date,
                                        'note': log.note})
                vals.update({'confirm': confirms})
                vals.update({'refuse': refuses})
                ret[po.id] = vals
                
        return ret
    
    """ write the priority of the record according to its state and the values of 'order' list variable """
    def _get_state_order(self, cr, uid, ids, name, args, context=None):
        order = ['draft','wait','approved','done','cancel']
        max_order = len(order)
        ret = {}.fromkeys(ids, max_order)
        for purchase in self.browse(cr, uid, ids, context=context):
            ret[purchase.id] = order.index(purchase.state) if purchase.state in order else max_order
        return ret
    
    def _get_reception_progress(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, 0.0)
        for purchase in self.browse(cr, uid, ids, context=context):
            total_qties = 0.0
            received_qties = 0.0
            for picking in purchase.picking_ids:
                for move in picking.move_lines:
                    total_qties += move.product_qty
                    if move.state in ('done','cancel'):
                        received_qties += move.product_qty
            val = 0
            if total_qties > 0.0:
                val = (received_qties / total_qties) * 100.0
            ret[purchase.id] = val
        return ret
    
    _columns = {
            'validation':fields.selection(AVAILABLE_ETAPE_VALIDATION, 'Etape Validation', readonly=True),
            'state_order': fields.function(_get_state_order, method=True, type='integer', string="Order", store=True),
            'service_id':fields.many2one('openstc.service', 'Service Demandeur', required=True),
            'user_id':fields.many2one('res.users','Personnel Demandeur', required=True),
            'description':fields.char('Objet de l\'achat',size=128),
            'po_ask_id':fields.many2one('purchase.order.ask', 'Demande de Devis Associée'),
            'po_ask_date':fields.related('po_ask_id','date_order', string='Date Demande Devis', type='date'),

            'account_analytic_id':fields.many2one('crossovered.budget.lines', 'Ligne Budgétaire Par défaut', help="Ligne Budgétaire par défaut pour les lignes d'achat."),
            'need_confirm':fields.function(_get_need_confirm, type='boolean', method=True, string='Need Validation ?'),

            'current_url':fields.char('URL Courante',size=256),
            'justif_check':fields.text('Justification de la décision de l\'Elu'),
            'all_budget_dispo':fields.function(_get_all_budget_dispo, type='boolean',string='All Budget Dispo ?', method=True),
            'elu_id':fields.many2one('res.users','Elu Concerné', readonly=True),
            'property_accountant_id':fields.property('res.users', type="many2one", relation="res.users", view_load=True, string='Accountant', required=True),
            'mail_sent':fields.boolean('Mail sent ?', invisible=True),
            'supplier_mail_sent':fields.boolean('Mail sent to supplier ?', invisible=True),
            
            #fields moved from open.engagement
            'date_engage_validated':fields.date('Date Validation de la commande', readonly=True),
            'date_engage_sent':fields.date('Date engagement commande', readonly=True),
            'date_engage_done':fields.datetime('Date de Cloture de la commande',readonly=True),
            'reception_ok':fields.boolean('Tous les Produits sont réceptionnés', readonly=True),
            'justificatif_refus':fields.text('Justification de votre Refus pour Paiement'),
            'engage_lines':fields.one2many('open.engagement.line','engage_id',string='Numéros d\'Engagements'),
            'attach_ids':fields.function(_get_engage_attaches, multi="attaches", type='one2many', relation='ir.attachment',string='Documents Joints'),
            'id':fields.integer('Id'),
            'current_url':fields.char('URL Courante',size=256),
            
            'attach_not_invoices': fields.function(_get_engage_attaches, multi="attaches", type="char", string="misc. attaches"),
            'attach_invoices': fields.function(_get_engage_attaches, multi="attaches", type="char", string="PDF invoice attaches"),
            'attach_waiting_invoice_ids': fields.function(_get_engage_attaches, multi="attaches", type="char", string="PDF invoice attaches to treat"),
            'engage_to_treat':fields.function(_get_engage_attaches, fnct_search=_search_engage_to_treat, multi="attaches", type='boolean', string='Engage to Treat', method=True),
            'all_invoices_treated':fields.function(_get_engage_attaches, fnct_search=search_all_invoices_treated, multi="attaches",type="boolean",string="All invoices treated", method=True),
            
            'validation_order_id': fields.many2one('openbase.validation', 'Validation process'),
            'validation_note': fields.text('Validation note'),
            'validation_order_items': fields.function(_get_validation_order_items, method=True, type='char', string='Validation Items'),
            #'reception_progress': fields.function(_get_reception_progress, method=True, type='float', string='Reception progress (%)'),
            }
    _defaults = {
#        'check_dst':lambda *a: False,
        'validation':'budget_to_check',
        'user_id': lambda self, cr, uid, context: uid,
        'service_id': lambda self, cr, uid, context: self.pool.get("res.users").browse(cr, uid, uid, context).service_ids and self.pool.get("res.users").browse(cr, uid, uid, context).service_ids[0].id or False,
        'name': lambda self, cr, uid, context: self._custom_sequence(cr, uid, context),
        'mail_sent' : lambda *a: False,
        'invoice_method': lambda *a: 'picking',
        }

    _actions = {
        'delete': lambda self,cr,uid,record,groups_code: record.state == 'cancel',
        'cancel': lambda self,cr,uid,record,groups_code: record.state in ('draft',),
        'confirm': lambda self,cr,uid,record,groups_code: record.state in ('wait',) and record.validation_order_id and bool(record.validation_order_id.current_user_item_id),
        'refuse': lambda self,cr,uid,record,groups_code: record.state in ('wait',) and record.validation_order_id and bool(record.validation_order_id.current_user_item_id),
        'done': lambda self,cr,uid,record,groups_code: record.state in ('approved',) and record.all_invoices_treated,
        'receive': lambda self,cr,uid,record,groups_code: record.state in ('approved',) and not record.shipped,
        'manage_invoice': lambda self,cr,uid,record,groups_code: record.state in ('approved','done'),
        'send_mail': lambda self,cr,uid,record,groups_code: record.state in ('approved',) and not record.supplier_mail_sent,
        'send_mail_again': lambda self,cr,uid,record,groups_code: record.state in ('approved',) and record.supplier_mail_sent
        }
    
    ##@return: internally used to add default values not sent from the GUI to the create() method of OpenERP
    def get_create_default_values(self, cr, uid, vals, context=None):
        ret = vals.copy()
        partner_id = vals.get('partner_id',False)
        partner_obj = self.pool.get('res.partner')
        if partner_id:
            partner = partner_obj.browse(cr, uid, partner_id, context=context)
            
            ret.update({'partner_address_id':partner_obj.address_get(cr, uid, [partner_id], ['default'])['default'],
                        'pricelist_id':partner.property_product_pricelist_purchase.id,
                        'location_id':partner.property_stock_customer.id})
        return ret
    
    ##@note: Override of create() method to add custom behavior : compute default value of 'name' using 'service_id' and compute value of 'current_url'
    def create(self, cr, uid, vals, context=None):
        if 'service_id' in vals and 'name' in vals:
           service = self.pool.get("openstc.service").browse(cr, uid, vals['service_id'], context=context)
           vals['name'] = vals['name'].replace('xxx',self.remove_accents(service.name[:3]).upper())
        else:
            default_search = []
            if 'service_id' in vals:
                service = self.pool.get("openstc.service").browse(cr, uid, vals['service_id'], context=context)
            else:
                defaults = self.default_get(cr, uid, ['user_id','service_id'], context=context)
                service = self.pool.get("openstc.service").browse(cr, uid, defaults['service_id'], context=context)
            if 'name' in vals:
                vals['name'] = vals['name'].replace('xxx',self.remove_accents(service.name[:3]).upper())
            else:
                defaults = self.default_get(cr, uid, ['name'], context=context)
                vals['name'] = defaults['name'].replace('xxx',self.remove_accents(service.name[:3]).upper())
            
        vals = self.get_create_default_values(cr, uid, vals, context=context)
        po_id = super(purchase_order, self).create(cr, uid, vals, context)
        self.write(cr, uid, [po_id],{'current_url':self.compute_current_url(cr, uid, po_id, context)}, context=context)
        return po_id
    
    def perform_wkf_evolve(self, cr, uid, ids, wkf_evolve, context=None):
        wkf_service = netsvc.LocalService('workflow')
        for id in ids:
            wkf_service.trg_validate(uid, 'purchase.order', id, wkf_evolve, cr)
        return True
    
    def perform_validation_wkf_evolve(self, cr, uid, ids, wkf_evolve, note='', context=None):
        wkf_service = netsvc.LocalService('workflow')
        for po in self.browse(cr, uid, ids, context=context):
            if po.validation_order_id:
                if hasattr(po.validation_order_id, wkf_evolve + '_note'):
                    po.validation_order_id.write({wkf_evolve + '_note': note})
                wkf_service.trg_validate(uid, 'openbase.validation', po.validation_order_id.id, wkf_evolve, cr)
        return True
    
    def write(self, cr, uid, ids, vals, context=None):
        if not context:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]
        wkf_evolve = False
        if 'wkf_evolve' in vals:
            wkf_evolve = vals.pop('wkf_evolve')
        note = vals.pop('validation_note') if 'validation_note' in vals else ''
        
        super(purchase_order, self).write(cr, uid, ids, vals, context)
        validation_wkf_evolve = ['confirm','refuse']
        if wkf_evolve and wkf_evolve != 'receive' and wkf_evolve not in validation_wkf_evolve:
            self.perform_wkf_evolve(cr, uid, ids, wkf_evolve, context=context)
        elif wkf_evolve == 'receive':
            self.create_stock_partial_picking(cr, uid, ids, context=context)
        elif wkf_evolve in validation_wkf_evolve:
            self.perform_validation_wkf_evolve(cr, uid, ids, wkf_evolve, note=note, context=context)
            
        return True
    
    def search(self, cr, uid, args=[],offset=0,limit=None, order=None,context=None, count=False):
        if context and context is not None:
            if 'only_engage_todo' in context:
                my_args = [('engage_to_treat','=',True)]
                return super(purchase_order, self).search(cr, uid, args + my_args, offset=offset, limit=limit, order=order,context=context,count=count)
        return super(purchase_order, self).search(cr, uid, args, offset=offset, limit=limit, order=order,context=context,count=count)
    
    
#    def wkf_confirm_order(self, cr, uid, ids, context=None):
#        ok = True
#        res = False
#        for po in self.browse(cr, uid, ids):
#            #TOCHECK: no need budget and engage validation if purchase order amount equals zero ?
#            if po.validation <> 'done' and po.amount_total > 0.0:
#                ok = False
#                if po.validation == 'budget_to_check':
#                    raise osv.except_osv(_('Budget to check'),_('Budgets must be checked and available for this purchase'))
#                elif po.validation == 'engagement_to_check':
#                    raise osv.except_osv(_('Purchase to check'),_('Purchase must be check and validated for this purchase'))
#            elif po.amount_total > 0.0:
#                self._create_report_attach(cr, uid, po, context)
#        if ok:
#             return super(purchase_order,self).wkf_confirm_order(cr, uid, ids, context)
#        return False
            
    def check_achat(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        #   Initialisation des seuils du user
#        seuils = self.pool.get("res.users").read(cr, uid, uid, ['max_po_amount','max_total_amount','company_id'], context)
#        company = self.pool.get("res.company").browse(cr, uid, seuils['company_id'][0], context)
#        #seuil par bon de commande
#        max_po_autorise = seuils['max_po_amount']
#        #seuil sur l'année
#        max_total_autorise = seuils['max_total_amount']
#        #Quota atteint sur l'année pour l'instant par l'utilisateur
#        user_po_ids = self.search(cr, uid, [('user_id','=',uid)], context)
#        total_po_amount = 0
#        for user_po in self.read(cr, uid, user_po_ids, ['amount_total']):
#            total_po_amount += user_po['amount_total']
#        #On vérifie pour la commande en cours à la fois le seuil par commande et le seuil annuel
#        for po in self.browse(cr, uid, ids, context):
#            #Commande "hors_marché", soit lorsqu'une commande est crée avec une demande de devis
#            #if not po.po_ask_id:
#            return po.amount_total < company.base_seuil_po
#            #Commande dans le cadre d'un marché
#        #Si on arrive ici, c'est qu'il y a un pb (la commande n'est plus associée à l'engagement)
#        #TODO: mettre un message d'erreur, voir si on ne perds pas les instances de wkf

        return not self.browse(cr, uid, ids, context=context).need_confirm
    
    def check_all_dispo(self, cr, uid, ids, context):
        if not isinstance(ids, list):
            ids = [ids]
        #Si toutes les lignes sont ok et qu'on a au moins une ligne de commande: renvoie True, sinon False
        ok = True
        one_line = False
        for po in self.browse(cr, uid, ids, context):
            for line in po.order_line:
                one_line = True
                ok = ok and line.dispo or False
                    
        return ok and one_line
    
    def get_elu_attached(self, cr, uid, id, context=None):
        service_id = self.browse(cr, uid, id, context).service_id.id
        groups_id = self.pool.get("res.groups").search(cr, uid, [('name','like','%Elu%')], context=context)
        elu_id = self.pool.get("res.users").search(cr, uid, ['&',('service_ids','=',service_id),('groups_id','in',groups_id),('name','not like','%Admin')], context=context)
        return elu_id and elu_id[0] or False
    
    #Construction dynamique de l'url à envoyer dans les mails
    #http://127.0.0.1:8069/web/webclient/home#id=${object.id}&view_type=page&model=purchase.order
    def compute_current_url(self, cr, uid, id, context=None):
        web_root_url = self.pool.get('ir.config_parameter').get_param(cr, uid, 'web.base.url')
        model = self._name
        #does http protocol present in web_root_url ?
        if web_root_url.find("http") < 0:
            web_root_url = "http://" + web_root_url
        ret = "%s/web/webclient/home#id=%s&view_type=page&model=%s" % (web_root_url, id, model)
        return ret
    
#    def validate_po_invoice(self, cr, uid, ids,context=None):
#        wf_service = netsvc.LocalService('workflow')
#        if not isinstance(ids, list):
#            ids = [ids]
#        for po in self.browse(cr, uid, ids, context):
#            wf_service.trg_validate(po.user_id.id, 'purchase.order', po.id, 'purchase_confirm', cr)
#            wf_service.trg_write(po.user_id.id, 'purchase.order', po.id, cr)
#        #Il faut relire l'objet car une nouvelle donnée est apparue entre temps dans l'engagement, account_invoice_id
#        for po in self.browse(cr, uid, ids, context):
#            for inv in po.invoice_ids:
#                wf_service.trg_write(po.user_id.id, 'account.invoice', inv.id, cr)
#                wf_service.trg_validate(po.user_id.id, 'account.invoice', inv.id, 'invoice_open', cr)
#        if not po.invoice_ids:
#            raise osv.except_osv(_('Error'),_('An OpenERP Invoice associated to this purchase is needed, can not update budgets without'))
#        return True
    
    def create_engage(self, cr, uid, id, context=None):
        po = self.browse(cr, uid, id, context=context)
        if not context or context == None:
            context = {}
        res_id = 0
        service_id = po.service_id
        context.update({'user_id':uid,'service_id':service_id.id})
        #Création de l'engagement et mise à jour des comptes analytiques des lignes de commandes (pour celles ou rien n'est renseigné
        self.validated_engage(cr, uid, [id], context)
        return True
    
    def validated_engage(self, cr, uid, ids, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        #Creation of engage lines, grouped by budget_line instead of one per order_line
        if not context:
            context = {}
        #line_obj = self.pool.get("purchase.order.line")
        engage_line_obj = self.pool.get("open.engagement.line")
        account_amount = {}
        for po in self.browse(cr, uid, ids, context):
            for line in po.order_line:
                #We verify that budget is associated to a service
                if not line.budget_line_id.crossovered_budget_id.service_id:
                    raise osv.except_osv(_('Error'),_('Budget %s has not any service associated') % line.budget_line_id.name)
                #we group amount by budget
                account_amount.setdefault(line.budget_line_id.id,{'line_id':[],'service_id':0})
                account_amount[line.budget_line_id.id]['line_id'].append(line.id)
                account_amount[line.budget_line_id.id]['service_id'] = line.budget_line_id.crossovered_budget_id.service_id.id
            engage_line = []
            #we create associated engage lines
            for key, value in account_amount.items():
                context.update({'service_id':value['service_id']})
                engage_line.append(engage_line_obj.create(cr, uid, {'order_line':[(4,x) for x in value['line_id']]}, context=context))
            #And we associate engage.lines created to current purchase
            self.write(cr, uid, [po.id], {'engage_lines':[(4,x) for x in engage_line], 'date_engage_validated':fields.date.context_today(self, cr, uid, context)}, context=context)
            #self.validate_po_invoice(cr, uid, ids, context)
        return True
    
#    def openstc_confirm(self, cr, uid, ids, context=None):
#        if isinstance(ids, list):
#            ids = ids[0]
#        po = self.browse(cr, uid, ids, context)
#        line_errors = []
#        for line in po.order_line:
#            if not line.dispo:
#                line_errors.append(line.id)
#        if not line_errors:
#            #check if purchase need to be confirmed by DST and Elu
#            if po.need_confirm:
#                self.write(cr, uid, ids, {'validation':'engagement_to_check'}, context=context)
#                #TODO: send mail to DST ?
#            else:
#                engage_id = self.create_engage(cr, po.user_id.id, ids, context=context)
#                self.write(cr, uid, ids, {'validation':'done'}, context=context)
#                #self.validate_po_invoice(cr, uid, ids, context=context)
#        else:
#            msg_error = ""
#            cpt = 0
#            for error in self.pool.get("purchase.order.line").browse(cr, uid, line_errors):
#                cpt += 1
#                msg_error = "%s %s" %("," if cpt >1 else "", error.name)
#            raise osv.except_osv(_('Error'),_('Some purchase order lines does not match amount budget line available : %s') %(msg_error,))
#
#        return {'type':'ir.actions.act_window.close'}
    
    def prepare_validation_order(self, cr, uid, purchase, context=None):
        service = purchase.user_id and purchase.user_id.service_id or False
        vals = {}
        if service:
            vals.update({
                'validation_type': service.purchase_validation_type,
                'validation_item_ids':[(4,x.id) for x in service.purchase_validation_item_ids],
                'name': u'%s - %s' % (purchase.name or u'', purchase.description or u'')
            })
            
        return vals
    
    def create_validation_order(self, cr, uid, ids, context=None):
        #@todo: send mail to dst ?
        validation_obj = self.pool.get('openbase.validation')
        ret = False
        for purchase in self.browse(cr, uid, ids, context=context):
            vals = self.prepare_validation_order(cr, uid, purchase, context=context)
            if vals:
                validation_id = validation_obj.create(cr, uid, vals, context=context)
                purchase.write({'validation_order_id': validation_id})
                ret = validation_id if not ret else ret # get only the first one created, because wkf must be called with ids of length 1, and must return the subflow id to link with
        self.write(cr, uid, ids, {'state':'wait'},context=context)
        return ret
    
    def wkf_check_elu(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        self.write(cr, uid, ids, {'state':'wait'},context=context)
        #create sum'up report for elu
        po = self.browse(cr, uid, ids, context=context)
        po.write({'check_dst':True, 'elu_id':self.get_elu_attached(cr, uid, po.id, context=context)},context=context)
        #self._create_report_sumup_attach(cr, uid, engage, context)
        #send mail to 'elu' to ask its check
        template_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'openstc_achat_stock', 'openstc_email_template_engage_to_validate')[1]
        msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, ids, force_send=True, context=context)
        mail_sent = True
        if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
            mail_sent = False
        po.write({'mail_sent':mail_sent})
        return True
    
    def wkf_confirm_order(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'check_dst':True, 'check_elu':True})
        for po in self.browse(cr, uid, ids, context=context):
            self.create_engage(cr, po.user_id.id, po.id, context)
            self._create_report_attach(cr, uid, po, context)
        return super(purchase_order, self).wkf_confirm_order(cr, uid, ids, context=context)    
    
    def wkf_send_mail(self, cr, uid, ids, context=None):
        #TODO: send mail to supplier using a custom mail template
        self.write(cr, uid, ids, {'supplier_mail_sent':True}, context=context)
        return True
    
    def wkf_wait_send_mail(self, cr, uid, ids, context=None):
        
        return True
    
#    def check_elu(self, cr, uid, ids, context=None):
#        if isinstance(ids, list):
#            ids = ids[0]
#        po = self.browse(cr, uid, ids)
#        if not po.check_dst:
#            raise osv.except_osv(_('Error'),_('DST have to check purchase first'))
#        
#        po.write({'validation':'done','engage_id':engage_id,'check_elu':True})
#        #self.validate_po_invoice(cr, uid, ids, context=context)
#        return {
#                'type':'ir.actions.act_window.close',
#        }
    
    def _prepare_inv_line(self, cr, uid, account_id, order_line, context=None):
        ret = super(purchase_order, self)._prepare_inv_line(cr, uid, account_id, order_line, context)
        ret.update({'merge_line_ids':[(4,x.id)for x in order_line.merge_line_ids]})
        return ret
    
    def open_stock_moves(self, cr, uid, ids, context=None):
        stock_ids = []
        for po in self.browse(cr, uid, ids):
            lines = [x.id for x in po.order_line]
            stock_ids.extend(self.pool.get("stock.move").search(cr, uid, [('purchase_line_id','in',lines)]))

        #We modify the active_ids context key to bypass the stock_move step interface (wizard actually wait for stock_move active_ids)
        active_ids = context.get('active_ids',ids)
        active_model = context.get('active_model')
        context.update({'active_ids':stock_ids,'old_active_ids':active_ids,'active_model':'stock.move','old_active_model':active_model})
        if not 'active_id' in context:
            context.update({'active_id':ids[0]})
        return {
            'type':'ir.actions.act_window',
            'res_model':'stock.partial.move',
            'context':context,
            'view_mode':'form',
            'target':'new',
            }
    
    ## retrieve the main picking related to the purchase (the one with state <> 'done') and use it to create a partial.stock.picking
    ## @return: id the created stock.partial.picking
    def create_partial_picking(self, cr, uid, id, context=None):
        context = context or {}
        ret = False
        wizard_obj = self.pool.get('stock.partial.picking')
        picking_obj = self.pool.get('stock.picking')
        
        #retrieve working picking(s) (must be only one)
        picking_ids = picking_obj.search(cr, uid, [('purchase_id.id', '=',id), ('state','not in',('done', 'cancel'))], context=context) 
        #if 1 or more pickings are found, we create a partial_picking converting the context to be properly used by the openerp wizard
        if picking_ids:
            context.update({'active_ids':picking_ids, 'active_model': 'stock.picking'})
            vals = wizard_obj.default_get(cr, uid, ['picking_id', 'move_ids', 'date'], context=context)
            vals.update({'move_ids': [(0,0,x) for x in vals['move_ids']]})
            ret = wizard_obj.create(cr, uid, vals, context=context)
        return ret
    
    def write_ciril_engage(self, cr, uid, ids, context=None):
        ret = ''
        template = template_ciril_txt_file_engagement()
        mail_template_obj = self.pool.get('email.template')
        mail_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'openstc_achat_stock','openstc_email_template_purchase_engaged')[1]
        for po in self.browse(cr, uid, ids ,context=context):
            ret = template.create_file(po)
            #write file on remote CIRIL server
            base_path = '%s/%s/%s' % (os.getenv('HOME', '.'),config.options.get('openerp_ciril_repository',''),cr.dbname)
            file_path = '%s/todo/%s.txt' % (base_path,po.name.replace('/','_'))
            ret_file = open(file_path, 'w')
            ret_file.write(ret.encode('utf-8'))
            ret_file.close()
            #perform push of the created file
            try:
                ret = urllib2.urlopen('http://%s:%s/%s/%s' % (config.options.get('push_service_host','localhost'),
                                                          config.options.get('push_service_port','44001'),
                                                          config.options.get('push_service_base_url','push_service'),
                                                          cr.dbname))
            except URLError as e:
                raise osv.except_osv(_('Error'), _('Internal server error, please contact your supplier.\n Technical error : "%s"') % e.reason)
            if ret.getcode() != 200:
                raise osv.except_osv(_('Error'), _('Internal server error, please contact your supplier.\n Technical error : "%s"') % ret.read())
            shutil.copy(file_path, base_path + '/archive')
            os.remove(file_path)
            #indicates that engage is sent by buyer (to the accounting department)
            now = datetime.now().strftime('%Y-%m-%d')
            po.write({'validation':'purchase_engaged','date_engage_sent':now})
            #@todo: send mail to accounting department to notify that a new file can be imported to their 3rd part accounting software
            mail_template_obj.send_mail(cr, uid, mail_id, po.id, force_send=True, context=context)
        return {'type':'ir.actions.act_window_close'}
    
    def all_reception_done(self, cr, uid, ids):
        if isinstance(ids, list):
            ids = ids[0]
        #On vérifie que toutes le réceptions de produits sont faites
        po = self.browse(cr, uid, ids)
        for line in po.order_line:
            for move in line.move_ids:
                if move.state <> 'done':
                    return False
            #if not engage.reception_ok:
            #    self.write(cr, uid, ids, {'reception_ok':True})
        return True
    
    def engage_done(self, cr, uid, ids, context=None):
        po = self.browse(cr, uid, ids[0], context=context)
        self.write(cr, uid, ids, {'state':'done','date_engage_done':datetime.now(), 'validation': 'purchase_paid'})
        self.pool.get('ir.attachment').write(cr, uid, [x.id for x in po.attach_ids], {'engage_done':True}, context=context)
        return True
    
    
purchase_order()



