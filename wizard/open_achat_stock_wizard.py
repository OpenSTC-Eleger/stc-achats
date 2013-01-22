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


class purchase_order_ask_verif_budget(osv.osv_memory):
    _name = "purchase.order.ask.verif.budget"
    
    def _sel_account_user(self, cr, uid, context=None):
        #Récup des services du user
        user = self.pool.get("res.users").browse(cr, uid, uid)
        service_ids = [x.id for x in user.service_ids]
        if not service_ids:
            raise osv.except_osv('Erreur','Vous n\'etes associés a aucun service')
        #Recherche des comptes analytiques en rapport avec les services du user
        account_analytic_ids = self.pool.get("account.analytic.account").search(cr, uid, [('service_id','in',service_ids)])
        #Récup du nom complet (avec hiérarchie) des comptes, name_get renvoi une liste de tuple de la meme forme que le retour attendu de notre fonction
        account_analytic = self.pool.get("account.analytic.account").name_get(cr, uid,account_analytic_ids, context)
        return account_analytic
    
    _columns = {
            'analytic_account_id':fields.selection(_sel_account_user,'Compte associé à l\'achat', required=True),
            'po_ammount':fields.float('Montant de l\'achat', digits=(5,2)),
            'budget_dispo':fields.float('Budget Disponible', digits=(6,2)),
            'tx_erosion': fields.float('Taux Erosion de votre Service', digits=(2,2)),
            'service_id':fields.many2one('openstc.service',string="Service Demandeur"),
            'budget_dispo_info':fields.float('Budget Disponible', digits=(6,2), readonly=True),
            'tx_erosion_info': fields.float('Taux Erosion de votre Service', digits=(2,2), readonly=True),
     }
    
    def default_get(self, cr, uid, fields, context=None):
        ret = super(purchase_order_ask_verif_budget, self).default_get(cr, uid ,fields, context)
        if ('ammount_total') in context:
            ret.update({'po_ammount':context['ammount_total']})
        return ret
    
    def onchange_analytic_account_id(self, cr, uid, ids, analytic_account_id=False):
        #On récupère la ligne budgétaire en rapport a ce compte analytique 
        if analytic_account_id:
            line_id = self.pool.get("crossovered.budget.lines").search(cr, uid, [('analytic_account_id','=',analytic_account_id)])
            if not line_id:
                return {'warning':{'title':'Erreur','message':'Ce compte Analytique n appartient a aucune ligne budgetaire'}}
            if isinstance(line_id, list):
                line_id = line_id[0]
                #print("Warning, un meme compte analytique est present dans plusieurs lignes de budgets")
            line = self.pool.get("crossovered.budget.lines").browse(cr, uid, line_id)
            res = abs(line.planned_amount) - abs(line.practical_amount)
            #TODO: Intégrer le taux d'érosion d'un service
            return {'value':{'budget_dispo_info':res,'budget_dispo':res,'service_id':line.analytic_account_id.service_id.id}}
        return {'value':{}}
    
    def to_draft_engage(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        wizard = self.browse(cr, uid, ids)
        restant = wizard.budget_dispo - wizard.po_ammount
        if restant < 0:
            raise osv.except_osv('Erreur','Vous n\'avez pas le budget suffisant pour cet achat')
        if 'po_id' in context:
            po_values = {}
            engage_state = "waiting_invoice"
            #Vérif montant, si > 300€, nécessite validation DST et élu
            if wizard.po_ammount >= 300.0:
                po_values.update({'validation':'engagement_to_check'})
                engage_state = "to_validate"
            else:
                po_values.update({'validation':'done'})
            context.update({'user_id':uid,'service_id':wizard.service_id.id})
            #Création de l'engagement et mise à jour des comptes analytiques des lignes de commandes (pour celles ou rien n'est renseigné
            po_line_ids = self.pool.get("purchase.order.line").search(cr, uid, [('order_id','=',context['po_id']),('account_analytic_id','=',False)])
            self.pool.get("purchase.order.line").write(cr, uid, po_line_ids, {'account_analytic_id':wizard.analytic_account_id})
            res_id = self.pool.get("open.engagement").create(cr, uid, {'user_id':uid,
                                                                       'service_id':wizard.service_id.id,
                                                                       'purchase_order_id':context['po_id'],
                                                                       'state':engage_state}, context=context)
            po_values.update({'engage_id':res_id})
            self.pool.get("purchase.order").write(cr, uid, context['po_id'], po_values, context=context)
            return {
                'type':'ir.actions.act_window',
                'target':'new',
                'res_model':'open.engagement',
                'view_mode':'form',
                'res_id':res_id
                }
        raise osv.except_osv('Erreur','La Commande associée a été perdue, veuillez recommencer')
        return
    
purchase_order_ask_verif_budget()
    

class openstc_open_engage_refuse_inv_wizard(osv.osv_memory):
    _name = "openstc.open.engage.refuse.inv.wizard"
    _columns = {
        'justif_refuse':fields.text('Justificatif du Refus de paiement de la facture',required=True),
        }

    def to_refuse(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        wizard = self.browse(cr, uid, ids, context)
        if 'attach_id' in context:
            attach = self.pool.get("ir.attachment").browse(cr, uid, context['attach_id'], context)
            #On indique le msg que devra afficher le mail
            self.pool.get("open.engagement").write(cr, uid, attach.res_id, {'justificatif_refus':wizard.justif_refuse}, context=context)
        self.pool.get("ir.attachment").write(cr, uid, attach.id, {'justif_refuse':wizard.justif_refuse}, context=context)
        return self.pool.get("ir.attachment").refuse_invoice_to_pay(cr, uid, attach.id, context)

openstc_open_engage_refuse_inv_wizard()


class openstc_merge_line_ask_respond_wizard(osv.osv_memory):
    _name = "openstc.merge.line.ask.respond.wizard"
    _columns = {
        'merge_ask_ids':fields.many2many('openstc.merge.line.ask', 'merge_ask_line_response_ids','wizard_id','merge_id'),
        }

    def default_get(self, cr, uid, fields, context=None):
        ret = {}
        if 'merge_ask_ids' in context:
            ret.update({'merge_ask_ids':[(6,0,context['merge_ask_ids'])]})
        return ret

    def to_respond(self, cr, uid, ids, context):
        for wizard in self.browse(cr, uid, ids, context):
            merge_ids = [x.id for x in wizard.merge_ask_ids]
        return self.pool.get("openstc.merge.line.ask").to_respond(cr, uid, merge_ids, context)

openstc_merge_line_ask_respond_wizard()


#TDOO: Gérer les marchés  A Bons de Commandes
class openstc_merge_line_ask_po_wizard(osv.osv_memory):
    _name = "openstc.merge.line.ask.po.wizard"
    _columns = {
        'merge_ask_ids':fields.many2many('openstc.merge.line.ask', 'merge_ask_line_to_po_ids','wizard_id','merge_id'),
        #'market':fields.function(_calc_market, 'Marché Dispo pour l\'ensemble de ces Besoins', type='many2one'),
        }
    
    def default_get(self, cr, uid, fields, context=None):
        ret = {}
        if 'merge_ask_ids' in context:
            ret.update({'merge_ask_ids':[(6,0,context['merge_ask_ids'])]})
        return ret
    
    #simply create a new po_ask with prod_lines already set
    def to_po_ask(self, cr, uid, ids, context=None):
        prod_merges = {}
        for wizard in self.browse(cr, uid, ids, context):
            #merge lines ask
            for merge in wizard.merge_ask_ids:
                prod_merges.setdefault(merge.product_id.id,{'merge_line_ids':[],'qte':0.0})
                prod_merges[merge.product_id.id]['merge_line_ids'].append((4,merge.id))
                prod_merges[merge.product_id.id]['qte'] += merge.qty_remaining
            #create ask_lines actions
            values = []
            for key, value in prod_merges.items():
                values_temp = value
                values_temp.update({'product_id':key})
                values.append((0,0,values_temp))
            res_id = self.pool.get("purchase.order.ask").create(cr, uid, {'order_lines':values}, context)
        return {
                'type':'ir.actions.act_window',
                'res_model':'purchase.order.ask',
                'res_id': res_id,
                'view_type':'form',
                'view_mode':'form,tree',
                'target':'current',
            }
    
    def to_po(self, cr, uid, ids, context=None):
        #merge lines ask
        for wizard in self.browse(cr, uid, ids, context):
            pass
        #TODO: Check if a market already exist for ALL products of the merges    
        #create po and po_line according to the market
        return
    
openstc_merge_line_ask_po_wizard()

