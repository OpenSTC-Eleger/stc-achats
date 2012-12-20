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
#Objet gérant une demande de prix selon les normes pour les collectivités (ex: demander à 3 fournisseurs différents mini)
class purchase_order_ask(osv.osv):
    AVAILABLE_ETAT_PO_ASK = [('draft','Brouillon'),('waiting_supplier','Attente Choix du Fournisseur'),
                             ('waiting_purchase_order','Bon pour création de Commande'),('done','Bon de Commande Généré')]
    _name = "purchase.order.ask"
    
    _columns = {
        'order_lines':fields.one2many('purchase.order.ask.line','po_ask_id'),
        'name':fields.char('Nom',size=64, required=True),
        'state':fields.selection(AVAILABLE_ETAT_PO_ASK,'Etat', readonly=True),
        'suppliers_id':fields.one2many('purchase.order.ask.partners','po_ask_id','Fournisseurs potentiels'),
        'purchase_order_id':fields.many2one('purchase.order','Commande associée'),
    }
    _defaults={
            'state':'draft'
    }
    def _check_supplier_selection(self, cr, uid, ids, context=None):
        one_selection = True
        for ask in self.browse(cr, uid, ids):
            if ask.state <> 'draft':
                one_selection = False
                for line in ask.suppliers_id:
                    if line.selected:
                        if not one_selection:
                            one_selection = True
                        else:
                            return False
        return one_selection
    
    def send_ask(self, cr, uid, ids, context=None):
        #Envoi d'un mail aux 3 fournisseurs
        #Puis on passe à l'étape d'après
        ask_lines = []
        ask_partners = []
        for ask in self.browse(cr, uid, ids):
            ask_partners.extend([x.id for x in ask.suppliers_id])
            ask_lines.extend([x.id for x in ask.order_lines])
        self.pool.get("purchase.order.ask.partners").write(cr, uid, ask_partners, {'state':'waiting_selection'})
        self.pool.get("purchase.order.ask.line").write(cr, uid, ask_lines, {'state':'waiting_pu'})
        self.write(cr, uid ,ids, {'state':'waiting_supplier'})
        return"""  {
            'view_mode':'form',
            'target':'current',
            'res_model':'purchase.order.line',
            'res_id':ids[0]
            }"""
    
    def validate_supplier(self, cr, uid, ids, context=None):
        if not self._check_supplier_selection(cr, uid, ids, context):
            raise osv.except_osv('Erreur','Vous devez choisir un Fournisseur pour la suite et un seul.')
        self.write(cr, uid, ids, {'state':'waiting_purchase_order'})
        return
    
    def to_draft_po(self, cr, uid, ids, context=None):
        supplier_id = 0
        list_prod = []
        if isinstance(ids,list):
            ids = ids[0]
        ask = self.browse(cr, uid, ids)
        #On récupère le fournisseur sélectionné
        for line in ask.suppliers_id:
            if line.selected:
                supplier_id = line.partner_id.id
        #On récupère les produits demandés avec leur qté et PU
        for line in ask.order_lines:
            if line.price_unit <= 0.0:
                raise osv.except_osv('Erreur','Il manque le prix unitaire d\'un ou plusieurs produits')
            list_prod.append({'prod_id':line.product_id.id,'price_unit':line.price_unit,'qte':line.qte})    
        return {
            'view_mode':'form',
            'target':'current',
            'type':'ir.actions.act_window',
            'res_model':'purchase.order',
            'context':{'ask_supplier_id':supplier_id,
                       'ask_prod_ids':list_prod,
                       'ask_today':fields.date.context_today(self,cr,uid,context),
                       'po_ask_id':ids}
            }
    
    def cancel(self, cr, uid, ids, context=None):
        for ask in self.browse(cr, uid, ids):
            self.pool.get("purchase.order.ask.partners").write(cr, uid, [x.id for x in ask.suppliers_id], {'state':'draft'})
        self.write(cr, uid, ids, {'state':'draft'})
        return
   
purchase_order_ask()

class purchase_order_ask_line(osv.osv):
    _name = "purchase.order.ask.line"
    _columns = {
        'po_ask_id': fields.many2one('purchase.order.ask','Demande associée'),
        'product_id' : fields.many2one('product.product','Produit', required=True),
        'qte':fields.integer('Quantitié', required=True),
        'price_unit':fields.float('Prix Unitaire convenu',digit=(3,2)),
        'description':fields.char('Description',size=256),
        'date_order':fields.date('Date Souhaitée'),
        'state':fields.selection([('draft','Brouillon'),('waiting_pu','Attente PU'),('done','Terminé')], 'Etat',invisible=True)
        }
    
    _defaults = {
        'state':'draft'
        }
    
purchase_order_ask_line()


class purchase_order_ask_partners(osv.osv):
    _name = "purchase.order.ask.partners"
    _columns = {
            'po_ask_id':fields.many2one('purchase.order.ask', 'Demande associée'),
            'partner_id':fields.many2one('res.partner','Fournisseur', required=True),
            'partner_address_id':fields.many2one('res.partner.address','Contact', required=True),
            'selected':fields.boolean('Choisir ce fournisseur'),
            'state':fields.selection([('draft','Brouillon'),('waiting_selection','En Attente Sélection'),('done','Terminé')],
                                 'Etat',readonly=True, invisible=True),
            }
    _defaults = {
            'state':'draft'
    }
    
purchase_order_ask_partners()
#Surcharge de purchase.order pour ajouter les étapes de validation pour collectivités : 
#Vérif dispo budget, sinon blocage
#Vérif validation achat par DST + Elu si > 300 euros
class purchase_order(osv.osv):
    AVAILABLE_ETAPE_VALIDATION = [('budget_to_check','Budget A Vérfier'),('engagement_to_check','Engagement A Vérifier'),
                                  ('done','Bon de Commande Validable')]
    _inherit = 'purchase.order'
    _name = 'purchase.order'
    _columns = {
            'validation':fields.selection(AVAILABLE_ETAPE_VALIDATION, 'Etape Validation', readonly=True),
            'engage_id':fields.many2one('open.engagement','Engagement associé',readonly=True),
            }
    _defaults = {
        'validation':'budget_to_check'
        }
    
    def default_get(self, cr, uid, fields, context=None):
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
    
    def create(self, cr, uid, ids, context=None):
        po_id = super(purchase_order, self).create(cr, uid, ids, context)
        if 'po_ask_id' in context:
            self.pool.get("purchase.order.ask").write(cr ,uid, context['po_ask_id'], {'state':'done',
                                                                                      'purchase_order_id':po_id},context) 
        return po_id
    
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
    
    def verif_budget(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        po = self.browse(cr, uid, ids)
            
        return{
               'type':'ir.actions.act_window',
               'res_model': 'purchase.order.ask.verif.budget',
               'view_mode': 'form',
               'target':'new',
               'context': {'po_id': po.id, 'ammount_total':po.amount_total}
               }
    
    def open_engage(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        engage_id = self.pool.get("open.engagement").search(cr ,uid, [('purchase_order_id','=',ids)])
        #Si on a plus d'un id renvoyé, on affiche une liste plutot qu'un formulaire
        if isinstance(engage_id,list):
            #Il y a plusieurs ids
            if len(engage_id) > 1:
                return {
                'type':'ir.actions.act_window',
                'target':'new',
                'res_model':'open.engagement',
                'view_mode':'tree,form',
                'domain':[('id','in',engage_id)]
                }
            #Il n'y a qu'un seul id mais contenu dans une liste
            else:
                engage_id = engage_id[0]
        #Il n'y a bien qu'un seul id
        return {
            'type':'ir.actions.act_window',
            'target':'new',
            'res_model':'open.engagement',
            'res_id':engage_id,
            'view_mode':'form',
            }
purchase_order()

#Modèle d'un num d'engagement : YYYY-SER-xxx (YYYY: année, SER: service sur 3 lettres majuscules, xxx num incremental (=> id ?))
class open_engagement(osv.osv):
    
    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')
    
    def _custom_sequence(self, cr, uid, context):
        seq = self.pool.get("ir.sequence").next_by_code(cr, uid, 'engage.number',context)
        user = self.pool.get("res.users").browse(cr, uid, uid)
        prog = re.compile('[Oo]pen[a-zA-Z]{3}/[Mm]anager')
        service = None
        if 'service_id' in context:
            service = context['service_id']
        for group in user.groups_id:
            if prog.search(group.name):
                if isinstance(user.service_ids, list) and not service:
                    service = user.service_ids[0]
                else:
                    service = self.pool.get("openstc.service").browse(cr, uid, service)
                seq = seq.replace('-xxx-','-' + self.remove_accents(service.name[:3]).upper() + '-')
                
        return seq
    
    _AVAILABLE_STATE_ENGAGE = [('draft','Brouillon'),('to_validate','A Valider'),('done','Validé')]
    _name="open.engagement"
    #TODO: Voir si un fields.reference pourrait fonctionner pour les documents associés a l'engagement (o2m de plusieurs models)
    _columns = {
        'name':fields.char('Numéro Engagement', size=16, required=True),
        'description':fields.char('Objet de l\'achat', size=128),
        'service_id':fields.many2one('openstc.service','Service Demandeur', required=True),
        'user_id':fields.many2one('res.users', 'Personnel Engagé', required=True),
        'purchase_order_id':fields.many2one('purchase.order','Commandes associées'),
        'state':fields.selection(_AVAILABLE_STATE_ENGAGE, 'Etat', readonly=True),
        }
    _defaults = {
            'name':lambda self,cr,uid,context:self._custom_sequence(cr, uid, context),
            'state':'draft',
            }
    
    def unlink(self, cr, uid, ids, context=None):
        #Si on supprimer un engagement, on doit forcer les documents associés à en générer un autre
        #En principe, aucun engagement ne doit etre supprimé
        engages = self.browse(cr, uid, ids)
        for engage in engages:
            self.pool.get("purchase.order").write(cr, uid, engage.purchase_order_id.id, {'validation':'budget_to_check'}, context)
        return super(open_engagement, self).unlink(cr, uid, ids, context)
    
open_engagement()
    
