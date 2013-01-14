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

class purchase_order_line(osv.osv):
    _inherit = "purchase.order.line"
    _name = "purchase.order.line"
    
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
        #'analytic_account_id':fields.selection(_sel_account_user,'Compte associé à l\'achat'),
        'budget_dispo':fields.float('Budget Disponible', digits=(6,2)),
        'tx_erosion': fields.float('Taux Erosion de votre Service', digits=(2,2)),
        'budget_dispo_info':fields.related('budget_dispo', type="float", string='Budget Disponible', digits=(6,2), readonly=True),
        'tx_erosion_info': fields.related('tx_erosion', string='Taux Erosion de votre Service', type="float", digits=(2,2), readonly=True),
        'dispo':fields.boolean('Budget OK',readonly=True),
        'merge_line_ids':fields.one2many('openstc.merge.line.ask','po_line_id','Regroupement des Besoins'),
        'in_stock':fields.float('Qté qui sera Stockée', digits=(3,2)),
        'in_stock_info':fields.related('in_stock',type='float', digits=(3,2), string='Qté qui sera Stockée', readonly=True),
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
                    qte += merge_line.product_qty
                else:
                    raise osv.except_osv('Erreur','Vous avez associé des lignes de regroupement ne faisait pas référence au produit de la ligne de commande en cours')
            return qte_ref >= qte
        return False
    
    _constraints = [(_check_qte_merge_qte_po,'Erreur, la quantité du produit commandé est inférieure a la quantité obtenu par regroupement de la demande de différents services et sites',['product_id','merge_line_ids'])]
    
    def onchange_account_analytic_id(self, cr, uid, ids, account_analytic_id=False):
        #On récupère la ligne budgétaire en rapport a ce compte analytique 
        if account_analytic_id:
            line_id = self.pool.get("crossovered.budget.lines").search(cr, uid, [('analytic_account_id','=',account_analytic_id)])
            if not line_id:
                return {'warning':{'title':'Erreur','message':'Ce compte Analytique n appartient a aucune ligne budgetaire'}}
            if isinstance(line_id, list):
                line_id = line_id[0]
                #print("Warning, un meme compte analytique est present dans plusieurs lignes de budgets")
            line = self.pool.get("crossovered.budget.lines").browse(cr, uid, line_id)
            res = abs(line.planned_amount) - abs(line.practical_amount)
            res_erosion = abs(line.practical_amount) / abs(line.planned_amount) * 100
            #TODO: Intégrer le taux d'érosion d'un service
            return {'value':{'budget_dispo_info':res,'budget_dispo':res,'tx_erosion':res_erosion,'tx_erosion_info':res_erosion}}
        return {'value':{}}
    def onchange_product_id(self, cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order=False, fiscal_position_id=False, date_planned=False,
            name=False, price_unit=False, notes=False, context=None):
        
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
            ret.update({'warning':{'title':'Attention','message':'Le Besoin que vous avez recensé est supérieur A ce que vous voulez acheter.'}})
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
    AVAILABLE_ETAPE_VALIDATION = [('budget_to_check','Budget A Vérfier'),('engagement_to_check','Engagement A Vérifier'),
                                  ('done','Bon de Commande Validable')]
    _inherit = 'purchase.order'
    _name = 'purchase.order'
    _columns = {
            'validation':fields.selection(AVAILABLE_ETAPE_VALIDATION, 'Etape Validation', readonly=True),
            'engage_id':fields.many2one('open.engagement','Engagement associé',readonly=True),
            'service_id':fields.many2one('openstc.service', 'Service Demandeur', required=True),
            'user_id':fields.many2one('res.users','Personnel Demandeur', required=True),
            'description':fields.char('Description',size=128),
            'po_ask_id':fields.many2one('purchase.order.ask', 'Demande de Devis Associée'),
            'po_ask_date':fields.related('po_ask_id','date_order', string='Date Demande Devis', type='date'),
            }
    _defaults = {
        'validation':'budget_to_check',
        'user_id': lambda self, cr, uid, context: uid,
        'service_id': lambda self, cr, uid, context: self.pool.get("res.users").browse(cr, uid, uid, context).service_ids[0].id,
        }
    
    """def onchange_po_ask_id(self, cr, uid, ids, po_ask_id,order_line):
        ret = {}
        ask = self.browse(cr, uid, po_ask_id)
        list_suppliers = []
        #On récupère si possible le fournisseur associé aux marchands (ne fait rien si plusieurs fournisseurs sont retenus dans le marché)
        for partner in ask.suppliers_id:
            if partner.selected:
                list_suppliers.append(partner.partner_id.id)
        if len(list_suppliers) == 1:
            ret.update({'partner_id':list_suppliers[0]})
        line_ids = [x[1] for x in order_line]
        return"""
    
    """def default_get(self, cr, uid, fields, context=None):
        ret = super(purchase_order,self).default_get(cr, uid, fields, context=context)
        if ('ask_supplier_id' and 'ask_prod_ids' and 'ask_today') in context:
            pricelist_id = self.onchange_partner_id(cr, uid, [], context['ask_supplier_id'])['value']['pricelist_id']
            prod_actions = []
            pol_obj = self.pool.get("purchase.order.line")
            for prod_ctx in context['ask_prod_ids']:
                prod_values = pol_obj.onchange_product_id(cr, uid, [], pricelist_id, prod_ctx['prod_id'], prod_ctx['qte'],
                                                           False, context['ask_supplier_id'], price_unit=prod_ctx['price_unit'],
                                                           date_order=context['ask_today'], context=context)['value']
                prod_values.update({'price_unit':prod_ctx['price_unit'], 'product_id':prod_ctx['prod_id']})
                prod_actions.append((0,0,prod_values))
            ret.update({'partner_id':context['ask_supplier_id'], 'order_line':prod_actions})
        return ret
    """
    def create(self, cr, uid, vals, context=None):
        """#Si un marché est renseigné, il faut forcer les prix unitaires aux valeurs négociées avec le fournisseur pour chaque produit
        #TOCHECK: Si un produit n'est pas dans le marché, permettre tout de même la commande ? Pour l'instant on considère que oui            """
        po_id = super(purchase_order, self).create(cr, uid, vals, context)
        """po = self.browse(cr, uid, po_id)
        ask_prods = {}
        values = []
        #Si un marché est renseigné
        if po.po_ask_id and not 'from_ask' in context:
            #Si True, on envoie un msg au user pour lui indiquer qu'on a forcé le price_unit de certaines lignes de commandes
            warning = False
            #récup des produits et de leur prix unitaire convenu avec le fournisseur
            for line in po.po_ask_id.order_lines:
                ask_prods.update({line.product_id.id:line.price_unit})
            #Récup des lines de commandes dont on doit forcer le price_unit
            for line in po.order_line:
                if line.product_id.id in ask_prods and line.price_unit <> ask_prods[line.product_id.id]:
                    warning = True
                    values.append((1,line.id,{'price_unit':ask_prods[line.product_id.id]}))
            context.update({'no_ask_validation':'1'})
            super(purchase_order, self).write(cr, uid, [po_id], {'order_line':values, 'validation':'budget_to_check'})
            if warning:
                self.log(cr, uid, po_id, 'Les prix unitaires de certaines lignes de la commande %s ont été modifiés' (po.name))
        """
        return po_id

    def write(self, cr, uid, ids, vals, context=None):
        """#Si un marché est renseigné, il faut forcer les prix unitaires aux valeurs négociées avec le fournisseur pour chaque produit
        #TOCHECK: Si un produit n'est pas dans le marché, permettre tout de même la commande ? Pour l'instant on considère que oui            """
        if not isinstance(ids, list):
            ids = [ids]
        super(purchase_order, self).write(cr, uid, ids, vals, context)
        """#On ne mets à jour les lignes de commandes seulement si le user veut sauvegarder le le formulaire, sinon
        #On doit passer no_ask_validation dans le context pour schunter cette étape
        if context and  not 'no_ask_validation' in context or not context:
            for po in self.browse(cr, uid, ids):
                ask_prods = {}
                values = []
                #Si un marché est renseigné
                if po.po_ask_id:
                    #Si True, on envoie un msg au user pour lui indiquer qu'on a forcé le price_unit de certaines lignes de commandes
                    warning = False
                    #récup des produits et de leur prix unitaire convenu avec le fournisseur
                    for line in po.po_ask_id.order_lines:
                        ask_prods.update({line.product_id.id:line.price_unit})
                    #Récup des lines de commandes dont on doit forcer le price_unit
                    for line in po.order_line:
                        if line.product_id.id in ask_prods and line.price_unit <> ask_prods[line.product_id.id]:
                            warning = True
                            values.append((1,line.id,{'price_unit':ask_prods[line.product_id.id]}))
                    
                    super(purchase_order, self).write(cr, uid, [po.id], {'order_line':values})
                    if warning:
                        self.log(cr, uid, po.id, 'Les prix unitaires de certaines lignes de la commande %s ont été modifiés' % (po.name))
                #super(purchase_order, self).write(cr, uid, po.id, {'order_line':[(1,x.id,{'dispo':False}) for x in po.order_line]})
        else:
            del(context['no_ask_validation'])"""
        return True
    
    
    def wkf_confirm_order(self, cr, uid, ids, context=None):
        ok = True
        for po in self.browse(cr, uid, ids):
            if po.validation <> 'done':
                ok = False
                if po.validation == 'budget_to_check':
                    raise osv.except_osv('Budget A Vérifier','Le Budget doit être vérifié et disponible pour valider un Bon de Commande')
                elif po.validation == 'engagement_to_check':
                    raise osv.except_osv('Engagement A Vérifier','L\'engagement doit être vérifié et compet pour valider un Bon de Commande')
        if ok:
            return super(purchase_order,self).wkf_confirm_order(cr, uid, ids, context)
    
    """
    indique si engagement validable sans signature Elu + DST ou non
    Si commande hors marché : True si < 300€ Sinon False
    Sinon : True si montant commande <= seuil max par commande de l'acheteur
                ET si montant commandes de l'années en cours <= seuil max annuel de l'acheteur
            Sinon False
    @return bool: True si validable directement, False sinon
    """
    def check_achat(self, cr, uid, ids, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        #   Initialisation des seuils du user
        seuils = self.pool.get("res.users").read(cr, uid, uid, ['max_po_amount','max_total_amount'], context)
        #seuil par bon de commande
        max_po_autorise = seuils['max_po_amount']
        #seuil sur l'année
        max_total_autorise = seuils['max_total_amount']
        #Quota atteint sur l'année pour l'instant par l'utilisateur
        user_po_ids = self.search(cr, uid, [('user_id','=',uid)], context)
        total_po_amount = 0
        for user_po in self.read(cr, uid, user_po_ids, ['amount_total']):
            total_po_amount += user_po['amount_total']
        #On vérifie pour la commande en cours à la fois le seuil par commande et le seuil annuel
        for po in self.browse(cr, uid, ids, context):
            #Commande "hors_marché", soit lorsqu'une commande est crée avec une demande de devis
            #if not po.po_ask_id:
            if po.po_ask_id:
                return po.amount_total < 300
            #Commande dans le cadre d'un marché
            else:
                #Test seuil par bon de commande
                if po.amount_total > max_po_autorise :
                    return False
                #Test seuil annuel
                elif po.amount_total + total_po_amount > max_total_autorise:
                    return False
                #Dans ce cas tout est ok, on peut valider automatiquement l'engagement
                return True
        #Si on arrive ici, c'est qu'il y a un pb (la commande n'est plus associée à l'engagement)
        #TODO: mettre un message d'erreur, voir si on ne perds pas les instances de wkf
        return False
    
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
            restant = -1
            if not line.account_analytic_id.id in dict_line_account:
                restant = line.budget_dispo - line.price_subtotal
            else:
                restant = dict_line_account[line.account_analytic_id.id] - line.price_subtotal
            dict_line_account.update({line.account_analytic_id.id:restant})
            if restant >= 0:
                line_ok.append(line.id)
            else:
                line_not_ok.append(line.id)
                #raise osv.except_osv('Erreur','Vous n\'avez pas le budget suffisant pour cet achat:' + line.name + ' x ' + str(line.product_qty) + '(' + str(line.price_subtotal) + ' euros)')
        self.pool.get("purchase.order.line").write(cr, uid, line_ok, {'dispo':True})
        self.pool.get("purchase.order.line").write(cr, uid, line_not_ok, {'dispo':False})
        """if not line_not_ok:
            self.write(cr, uid, ids, {'validation':'engagement_to_check'})"""
        return not line_not_ok
    
    def open_engage(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        po = self.browse(cr, uid, ids, context)
        if self.verif_budget(cr, uid, ids, context):
            #On vérifie si on a un budget suffisant pour chaque ligne d'achat
            #On gère aussi le cas de plusieurs lignes référants au même compte analytique
            if not po.engage_id:
                service_id = po.service_id
                context.update({'user_id':uid,'service_id':service_id.id})
                #Création de l'engagement et mise à jour des comptes analytiques des lignes de commandes (pour celles ou rien n'est renseigné
                res_id = self.pool.get("open.engagement").create(cr, uid, {'user_id':uid,
                                                                           'service_id':service_id.id,
                                                                           'purchase_order_id':ids}, context)
                if res_id:
                    engage = self.pool.get("open.engagement").read(cr, uid, res_id, ['name'])
                    self.log(cr, uid, ids, 'Le Bond d\'engagement Numéro %s a été créé le %s' % (engage['name'], datetime.now()))
            else:
                res_id = po.engage_id.id
            return {
                'type':'ir.actions.act_window',
                'target':'new',
                'res_model':'open.engagement',
                'view_mode':'form',
                'res_id':res_id
                }
        #else:
            #raise osv.except_osv('Erreur','Une partie de votre commande ne rentre pas dans votre budget.')
            #self.write(cr, uid, ids, {'validation':'budget_to_check'}, context)
            #self.pool.get("purchase.order.line").write(cr, uid, [x.id for x in po.order_line], {'dispo':False})
        return
        
    def action_invoice_create(self, cr, uid, ids, context=None):
        inv_id = super(purchase_order, self).action_invoice_create(cr, uid, ids, context)
        for purchase in self.browse(cr, uid, ids, context):
            self.pool.get("open.engagement").write(cr, uid, purchase.engage_id.id, {'account_invoice_id':inv_id})
        return inv_id
    
    def _prepare_inv_line(self, cr, uid, account_id, order_line, context=None):
        ret = super(purchase_order, self)._prepare_inv_line(cr, uid, account_id, order_line, context)
        ret.update({'merge_line_ids':[(4,x.id)for x in order_line.merge_line_ids]})
        return ret
    
purchase_order()



