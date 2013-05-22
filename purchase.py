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
import netsvc
import unicodedata
import time
import base64
from tools.translate import _
from ciril_template_files import template_ciril_txt_file_engagement

class purchase_order_line(osv.osv):
    _inherit = "purchase.order.line"
    _name = "purchase.order.line"

    
    def _get_budget_dispo(self, cr, uid, ids, name ,args, context=None):
        ret = {}.fromkeys(ids, 0.0)
        for line in self.browse(cr, uid, ids, context):
            #we compute only for draft purchases 
            if not line.order_id or line.order_id.state == 'draft':
                line_id = self.pool.get("crossovered.budget.lines").search(cr, uid, [('analytic_account_id','=',line.account_analytic_id.id)])
                if line_id:
                    #return {'warning':{'title':'Erreur','message':'Ce compte Analytique n appartient a aucune ligne budgetaire'}}
                    if isinstance(line_id, list):
                        line_id = line_id[0]
                    budget_line = self.pool.get("crossovered.budget.lines").browse(cr, uid, line_id)
                    res = abs(budget_line.planned_amount) - abs(budget_line.openstc_practical_amount)
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
            if not context:
                context = {}
            context.update({'no_ask_validation':'1'})
            if budget_to_check:
                self.pool.get("purchase.order").write(cr, uid, line.order_id.id, {'validation':'budget_to_check'},context)
            #Récup du ou des Bons de Commandes associées aux lignes de Commandes (parametre ids)
        return True
    
purchase_order_line()

#Surcharge de purchase.order pour ajouter les étapes de validation pour collectivités : 
#Vérif dispo budget, sinon blocage
#Vérif validation achat par DST + Elu si > 300 euros (EDIT: voir modifs ALAMICHEL dans son mail)
class purchase_order(osv.osv):
    
    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')
    
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
    
    AVAILABLE_ETAPE_VALIDATION = [('budget_to_check','Budget A vérfier'),('engagement_to_check','Commande A signer'),
                                  ('done','Commande validée')]
    _inherit = 'purchase.order'
    _name = 'purchase.order'
    
    def _get_need_confirm(self, cr, uid, ids, name, args, context=None):
        ret = {}
        for po in self.browse(cr, uid, ids, context=context):
            if po.user_id and po.user_id.max_po_amount_no_market:
                ret[po.id] = po.user_id.max_po_amount_no_market <= po.amount_total
            else:
                ret[po.id] = True
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
    
    def button_dummy(self, cr, uid, ids, context={}):
        display = False
        if context:
            display = 'display_popup' in context
        for po in self.browse(cr, uid, ids, context=context):
            for line in po.order_line:
                if not line.budget_line_id and display:
                    raise osv.except_osv(_('Error'),_('There is missing budget attributions in order lines'))
        return {'type':'ir.actions.act_window.close'}
    
    _columns = {
            'validation':fields.selection(AVAILABLE_ETAPE_VALIDATION, 'Etape Validation', readonly=True),
            'engage_id':fields.many2one('open.engagement','Suivi commande associé',readonly=True),
            'service_id':fields.many2one('openstc.service', 'Service Demandeur', required=True),
            'user_id':fields.many2one('res.users','Personnel Demandeur', required=True),
            'description':fields.char('Objet de l\'achat',size=128),
            'po_ask_id':fields.many2one('purchase.order.ask', 'Demande de Devis Associée'),
            'po_ask_date':fields.related('po_ask_id','date_order', string='Date Demande Devis', type='date'),
            #'account_analytic_id':fields.many2one('account.analytic.account', 'Ligne Budgétaire Par défaut', help="Ligne Budgétaire par défaut pour les lignes d'achat."),
            'account_analytic_id':fields.many2one('crossovered.budget.lines', 'Ligne Budgétaire Par défaut', help="Ligne Budgétaire par défaut pour les lignes d'achat."),
            'need_confirm':fields.function(_get_need_confirm, type='boolean', method=True, string='Need Validation ?'),
            'check_dst':fields.boolean('Signature DST'),
            'current_url':fields.char('URL Courante',size=256),
            'elu_id':fields.many2one('res.users','Elu Concerné', readonly=True),
            'justif_check':fields.text('Justification de la décision de l\'Elu'),
            'all_budget_dispo':fields.function(_get_all_budget_dispo, type='boolean',string='All Budget Dispo ?', method=True),
            'elu_id':fields.many2one('res.users','Elu Concerné', readonly=True),

            }
    _defaults = {
        'check_dst':lambda *a: False,
        'validation':'budget_to_check',
        'user_id': lambda self, cr, uid, context: uid,
        'service_id': lambda self, cr, uid, context: self.pool.get("res.users").browse(cr, uid, uid, context).service_ids and self.pool.get("res.users").browse(cr, uid, uid, context).service_ids[0].id or False,
        'name': lambda self, cr, uid, context: self._custom_sequence(cr, uid, context)
        }

    
    def create(self, cr, uid, vals, context=None):
        if 'service_id' in vals and 'name' in vals:
           service = self.pool.get("openstc.service").browse(cr, uid, vals['service_id'], context=context)
           vals['name'] = vals['name'].replace('xxx',self.remove_accents(service.name[:3]).upper())
        else:
            default_search = []
            if 'service_id' in vals:
                service = service = self.pool.get("openstc.service").browse(cr, uid, vals['service_id'], context=context)
            else:
                defaults = self.default_get(cr, uid, ['user_id','service_id'], context=context)
                service = self.pool.get("openstc.service").browse(cr, uid, defaults['service_id'], context=context)
            if 'name' in vals:
                vals['name'] = vals['name'].replace('xxx',self.remove_accents(service.name[:3]).upper())
            else:
                defaults = self.default_get(cr, uid, ['name'], context=context)
                vals['name'] = defaults['name'].replace('xxx',self.remove_accents(service.name[:3]).upper())
            
        po_id = super(purchase_order, self).create(cr, uid, vals, context)
        self.write(cr, uid, [po_id],{'current_url':self.compute_current_url(cr, uid, po_id, context)}, context=context)
        return po_id

    def write(self, cr, uid, ids, vals, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        super(purchase_order, self).write(cr, uid, ids, vals, context)
        return True
    
    
    def wkf_confirm_order(self, cr, uid, ids, context=None):
        ok = True
        res = False
        for po in self.browse(cr, uid, ids):
            #TOCHECK: no need budget and engage validation if purchase order amount equals zero ?
            if po.validation <> 'done' and po.amount_total > 0.0:
                ok = False
                if po.validation == 'budget_to_check':
                    raise osv.except_osv(_('Budget to check'),_('Budgets must be checked and available for this purchase'))
                elif po.validation == 'engagement_to_check':
                    raise osv.except_osv(_('Engage to check'),_('Engage must be check and validated for this purchase'))
            elif po.amount_total > 0.0:
                self._create_report_attach(cr, uid, po, context)
        if ok:
             return super(purchase_order,self).wkf_confirm_order(cr, uid, ids, context)
        return False
            
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
    
    def verif_budget(self, cr, uid, ids, context=None):
        line_ok = []
        line_not_ok = []
        
        dict_line_account = {}
        #On vérifie si on a un budget suffisant pour chaque ligne d'achat
        #On gère aussi le cas de plusieurs lignes référants au même compte analytique
        po = self.browse(cr, uid, ids)
        for line in po.order_line:
            #compute line amount with taxes
            amount_line = line.amount_ttc
            restant = -1
            if not line.account_analytic_id.id in dict_line_account:
                restant = line.budget_dispo - amount_line
            else:
                restant = dict_line_account[line.account_analytic_id.id] - amount_line
            dict_line_account.update({line.account_analytic_id.id:restant})
            if restant >= 0:
                line_ok.append(line.id)
            else:
                line_not_ok.append(line.id)
                #raise osv.except_osv('Erreur','Vous n\'avez pas le budget suffisant pour cet achat:' + line.name + ' x ' + str(line.product_qty) + '(' + str(line.price_subtotal) + ' euros)')
        self.pool.get("purchase.order.line").write(cr, uid, line_ok, {'dispo':True})
        self.pool.get("purchase.order.line").write(cr, uid, line_not_ok, {'dispo':False})
        return line_not_ok
    
    def get_elu_attached(self, cr, uid, id, context=None):
        service_id = self.browse(cr, uid, id, context).service_id.id
        groups_id = self.pool.get("res.groups").search(cr, uid, [('name','like','%Elu%')], context=context)
        elu_id = self.pool.get("res.users").search(cr, uid, ['&',('service_ids','=',service_id),('groups_id','in',groups_id),('name','not like','%Admin')], context=context)
        return elu_id and elu_id[0] or False
    
    #Construction dynamique de l'url à envoyer dans les mails
    #http://127.0.0.1:8069/web/webclient/home#id=${object.id}&view_type=page&model=open.engagement
    def compute_current_url(self, cr, uid, id, context=None):
        web_root_url = self.pool.get('ir.config_parameter').get_param(cr, uid, 'web.base.url')
        model = self._name
        #does http protocol present in web_root_url ?
        if web_root_url.find("http") < 0:
            web_root_url = "http://" + web_root_url
        ret = "%s/web/webclient/home#id=%s&view_type=page&model=%s" % (web_root_url, id, model)
        return ret
    
    def validate_po_invoice(self, cr, uid, ids,context=None):
        wf_service = netsvc.LocalService('workflow')
        if not isinstance(ids, list):
            ids = [ids]
        for po in self.browse(cr, uid, ids, context):
            wf_service.trg_validate(po.user_id.id, 'purchase.order', po.id, 'purchase_confirm', cr)
            wf_service.trg_write(po.user_id.id, 'purchase.order', po.id, cr)
        #Il faut relire l'objet car une nouvelle donnée est apparue entre temps dans l'engagement, account_invoice_id
        for po in self.browse(cr, uid, ids, context):
            for inv in po.invoice_ids:
                wf_service.trg_write(po.user_id.id, 'account.invoice', inv.id, cr)
                wf_service.trg_validate(po.user_id.id, 'account.invoice', inv.id, 'invoice_open', cr)
        if not po.invoice_ids:
            raise osv.except_osv(_('Error'),_('An OpenERP Invoice associated to this purchase is needed, can not update budgets without'))
        return True
    
    def create_engage(self, cr, uid, id, context=None):
        po = self.browse(cr, uid, id, context=context)
        res_id = 0
        if not po.engage_id:
                service_id = po.service_id
                context.update({'user_id':uid,'service_id':service_id.id})
                #Création de l'engagement et mise à jour des comptes analytiques des lignes de commandes (pour celles ou rien n'est renseigné
                res_id = self.pool.get("open.engagement").create(cr, uid, {'user_id':uid,
                                                                           'service_id':service_id.id,
                                                                           'purchase_order_id':po.id}, context)
                wf_service = netsvc.LocalService('workflow')
                wf_service.trg_validate(po.user_id.id, 'open.engagement', res_id, 'confirm', cr)
        else:
            res_id = po.engage_id.id
        return res_id
    
    def openstc_confirm(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        po = self.browse(cr, uid, ids, context)
        #line_errors = self.verif_budget(cr, uid, ids, context)
        line_errors = []
        for line in po.order_line:
            if not line.dispo:
                line_errors.append(line.id)
        if not line_errors:
            #check if purchase need to be confirmed by DST and Elu
            if po.need_confirm:
                self.write(cr, uid, ids, {'validation':'engagement_to_check', 'elu_id':self.get_elu_attached(cr, uid, po.id, context=context)}, context=context)
                #TODO: send mail to DST ?
            else:
                engage_id = self.create_engage(cr, uid, ids, context=context)
                self.write(cr, uid, ids, {'validation':'done','engage_id':engage_id}, context=context)
                self.validate_po_invoice(cr, uid, ids, context=context)
#            #On vérifie si on a un budget suffisant pour chaque ligne d'achat
#            #On gère aussi le cas de plusieurs lignes référants au même compte analytique
#            if not po.engage_id:
#                service_id = po.service_id
#                context.update({'user_id':uid,'service_id':service_id.id})
#                #Création de l'engagement et mise à jour des comptes analytiques des lignes de commandes (pour celles ou rien n'est renseigné
#                res_id = self.pool.get("open.engagement").create(cr, uid, {'user_id':uid,
#                                                                           'service_id':service_id.id,
#                                                                           'purchase_order_id':ids}, context)
#                if res_id:
#                    engage = self.pool.get("open.engagement").read(cr, uid, res_id, ['name'])
#                    self.log(cr, uid, ids, _('Engage %s was created at %s') % (engage['name'], datetime.now()))
#                    po.write({'validation':'engagement_to_check'})
#            else:
#                res_id = po.engage_id.id
#            return {
#                'type':'ir.actions.act_window',
#                'target':'current',
#                'res_model':'open.engagement',
#                'view_mode':'form',
#                'res_id':res_id
#                }
        else:
            msg_error = ""
            cpt = 0
            for error in self.pool.get("purchase.order.line").browse(cr, uid, line_errors):
                cpt += 1
                msg_error = "%s %s" %("," if cpt >1 else "", error.name)
            raise osv.except_osv(_('Error'),_('Some purchase order lines does not match amount budget line available : %s') %(msg_error,))

        return {'type':'ir.actions.act_window.close'}
    
    def action_dst_check(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        #create sum'up report for elu
        po = self.browse(cr, uid, ids, context=context)
        #self._create_report_sumup_attach(cr, uid, engage, context)
        #Envoi du mail A l'élu pour lui demande sa signature Apres signature du DST
        template_id = self.pool.get("email.template").search(cr, uid, [('model_id','=','purchase.order'),('name','like','%Elu%')], context=context)
        if isinstance(template_id, list):
            template_id = template_id[0]
        msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, ids, force_send=True, context=context)
        if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
            raise osv.except_osv(_('Error'),_('Error, fail to notify Elu by mail, your check is avoid for this time'))
            #return False
        po.write({'check_dst':True})
        #return True
        return {'type':'ir.actions.act_window.close'}
    
    def check_elu(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        po = self.browse(cr, uid, ids)
        if not po.check_dst:
            raise osv.except_osv(_('Error'),_('DST have to check purchase first'))
        engage_id = self.create_engage(cr, po.user_id.id, po.id, context)
        po.write({'validation':'done','engage_id':engage_id})
        self.validate_po_invoice(cr, uid, ids, context=context)
        return {
                'type':'ir.actions.act_window.close',
        }
    
#    def action_invoice_create(self, cr, uid, ids, context=None):
#        inv_id = super(purchase_order, self).action_invoice_create(cr, uid, ids, context)
#        for purchase in self.browse(cr, uid, ids, context):
#            self.pool.get("open.engagement").write(cr, uid, purchase.engage_id.id, {'account_invoice_id':inv_id})
#        return inv_id
    
    def write_ciril_engage(self, cr, uid, ids, context=None):
        ret = ''
        template = template_ciril_txt_file_engagement()
        
        for po in self.browse(cr, uid, ids ,context=context):
            ret += template.create_file(po.engage_id)
            #write content in an ir.attachment
            ret = base64.b64encode(ret)
            self.pool.get("ir.attachment").create(cr, uid, {'name':'engages.txt',
                                                            'datas_fname':'engages.txt',
                                                            'datas':ret,
                                                            'res_model':self._name,
                                                            'res_id':po.id
                                                            })
        return {'type':'ir.actions.act_window_close'}
    
    def _prepare_inv_line(self, cr, uid, account_id, order_line, context=None):
        ret = super(purchase_order, self)._prepare_inv_line(cr, uid, account_id, order_line, context)
        ret.update({'merge_line_ids':[(4,x.id)for x in order_line.merge_line_ids]})
        return ret
    
purchase_order()



