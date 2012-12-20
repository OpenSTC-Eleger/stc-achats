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
            res = line.planned_amount - abs(line.practical_amount)
            #Cela est seulement a titre d'infos pour le user
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
            engage_state = "done"
            if restant > 300.0:
                po_values.update({'validation':'engagement_to_check'})
                engage_state = "to_validate"
            else:
                po_values.update({'validation':'done'})
            context.update({'user_id':uid,'service_id':wizard.service_id.id})
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
    

