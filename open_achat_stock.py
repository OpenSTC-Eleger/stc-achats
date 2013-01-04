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
#Objet gérant une demande de prix selon les normes pour les collectivités (ex: demander à 3 fournisseurs différents mini)
class purchase_order_ask(osv.osv):
    AVAILABLE_ETAT_PO_ASK = [('draft','Brouillon'),('waiting_supplier','Attente Choix du Fournisseur'),
                             ('waiting_purchase_order','Bon pour création de Commandes'),('done','Marché Clos')]
    _name = "purchase.order.ask"
    
    _columns = {
        'order_lines':fields.one2many('purchase.order.ask.line','po_ask_id'),
        'name':fields.char('Nom',size=64, required=True),
        'sequence':fields.char('Numéro Marché',size=4, required=True),
        'state':fields.selection(AVAILABLE_ETAT_PO_ASK,'Etat', readonly=True),
        'suppliers_id':fields.one2many('purchase.order.ask.partners','po_ask_id','Fournisseurs potentiels'),
        'purchase_order_id':fields.many2one('purchase.order','Commande associée'),
        'date_order':fields.date('Date d\'Obtention du Marché', required=True),
    }
    _defaults={
            'state':'draft',
            'sequence': lambda self, cr, uid, context: self.pool.get("ir.sequence").next_by_code(cr, uid, 'marche.po.number',context),
            'date_order':lambda self, cr, uid, context: fields.date.context_today(self ,cr ,uid ,context)
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
    
    def name_get(self, cr, uid, ids, context=None):
        res = []
        for ask in self.read(cr, uid, ids,['id', 'name','sequence']):
            res.append((ask['id'], '%s : %s' % (ask['sequence'], ask['name'])))
        return res
    
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
        partner_infos = self.pool.get("purchase.order").onchange_partner_id(cr, uid, [], supplier_id)['value']
        prod_actions = []
        pol_obj = self.pool.get("purchase.order.line")
        for prod_ctx in list_prod:
            prod_values = pol_obj.onchange_product_id(cr, uid, [], partner_infos['pricelist_id'], prod_ctx['prod_id'], prod_ctx['qte'],
                                                       False, supplier_id, price_unit=prod_ctx['price_unit'],
                                                       date_order=fields.date.context_today(self,cr,uid,context), context=context)['value']
            prod_values.update({'price_unit':prod_ctx['price_unit'], 'product_id':prod_ctx['prod_id']})
            prod_actions.append((0,0,prod_values))
        entrepot_id = self.pool.get("stock.warehouse").search(cr, uid, [])
        if not entrepot_id:
            raise osv.except_osv('Erreur','Vous devez définir un entrepot dans la configuration OpenERP avant de continuer.')
        if isinstance(entrepot_id, list):
            entrepot_id = entrepot_id[0]
        entrepot_infos = self.pool.get("purchase.order").onchange_warehouse_id(cr, uid, [], entrepot_id)['value']
        ret = {'partner_id':supplier_id, 'po_ask_id':ask.id,'warehouse_id':entrepot_id,'order_line':prod_actions}
        ret.update(partner_infos)
        ret.update(entrepot_infos)
        context.update({'from_ask':'1'})
        po_id = self.pool.get("purchase.order").create(cr, uid, ret, context)
        """return {
            'view_mode':'form',
            'target':'current',
            'type':'ir.actions.act_window',
            'res_model':'purchase.order',
            'context':{'ask_supplier_id':supplier_id,
                       'ask_prod_ids':list_prod,
                       'ask_today':fields.date.context_today(self,cr,uid,context),
                       'po_ask_id':ids}
            }"""
        return {
            'view_mode':'form',
            'target':'current',
            'type':'ir.actions.act_window',
            'res_model':'purchase.order',
            'res_id':po_id
            }
    
    def do_terminate(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state':'done'})
        return
    
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
    
    _AVAILABLE_STATE_ENGAGE = [('draft','Brouillon'),('to_validate','A Valider'),('waiting_invoice','Attente Facture Fournisseur')
                               ,('waiting_reception','Attente Réception Produits et Facture Fournisseur incluse'),('engage_to_terminate','Engagement Bon Pour Paiement'),
                               ('waiting_invoice_validated','Attente Facture Fournisseur Validée par Acheteur'),('except_invoice','Refus pour Paiement'),
                               ('done','Clos')]
    _name="open.engagement"
    #TODO: Voir si un fields.reference pourrait fonctionner pour les documents associés a l'engagement (o2m de plusieurs models)
    _columns = {
        'name':fields.char('Numéro Engagement', size=16, required=True),
        'description':fields.related('purchase_order_id', 'description', string='Objet de l\'achat', type="char"),
        'service_id':fields.many2one('openstc.service','Service Demandeur', required=True),
        'user_id':fields.many2one('res.users', 'Personnel Engagé', required=True),
        'purchase_order_id':fields.many2one('purchase.order','Commande associée'),
        'account_invoice_id':fields.many2one('account.invoice','Facture (OpenERP) associée'),
        'check_dst':fields.boolean('Signature DST'),
        'date_invoice_received':fields.date('Date Réception Facture'),
        'state':fields.selection(_AVAILABLE_STATE_ENGAGE, 'Etat', readonly=True),
        'reception_ok':fields.boolean('Produits Réceptionnés', readonly=True),
        'invoice_ok':fields.boolean('Facture Founisseur Jointe', readonly=True),
        'justificatif_refus':fields.text('Justification de votre Refus pour Paiement'),
        }
    _defaults = {
            'name':lambda self,cr,uid,context:self._custom_sequence(cr, uid, context),
            'state':'draft',
            'user_id':lambda self,cr,uid,context:uid,
            }
    
    def check_achat(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        po_id = self.read(cr, uid, ids, ['purchase_order_id'])
        return self.pool.get("purchase.order").check_achat(cr, uid, po_id['purchase_order_id'][0], context)
    
    def check_elu(self, cr, uid, ids, context=None):
        po_ids = []
        for engage in self.browse(cr, uid, ids):
            if not engage.check_dst:
                raise osv.except_osv('Erreur','Le DST doit avoir signé l\'engagement avant que vous ne puissiez le faire')
            po_ids.append(engage.purchase_order_id.id)
            self.pool.get("purchase.order").write(cr, uid, po_ids, {'validation':'done'})
            wf_service = netsvc.LocalService('workflow')
            wf_service.trg_validate(uid, 'open.engagement', engage.id, 'signal_validated', cr)
        return
    
    def link_engage_po(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state':'to_validate'}, context)
        for engage in self.browse(cr, uid, ids, context):
            self.pool.get("purchase.order").write(cr, uid, engage.purchase_order_id.id, {'engage_id':engage.id}, context)
        return True
    
    def validated_engage(self, cr, uid, ids, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        po_ids = [x.purchase_order_id.id for x in self.browse(cr, uid, ids, context)]
        self.pool.get("purchase.order").write(cr ,uid, po_ids, {'validation':'done'}, context)
        return True
    
    def validate_po_invoice(self, cr, uid, ids,context=None):
        #Si il y a au moins une pièce jointe, on considère que la facture en fait partie (en principe, seule la facture doit y être ajoutée
        """if isinstance(ids, list):
            ids = ids[0]
        count = 0
        count_attachments = self.pool.get("ir.attachment").search(cr, uid, [('res_id','=',ids),('res_model','=',self._name)], count=True)
        if not count_attachments:
            raise osv.except_osv('Erreur','Vous n\'avez pas joint la facture reçue par votre founisseur.')"""
        wf_service = netsvc.LocalService('workflow')
        if not isinstance(ids, list):
            ids = [ids]
        for engage in self.browse(cr, uid, ids, context):
            wf_service.trg_validate(uid, 'purchase.order', engage.purchase_order_id.id, 'purchase_confirm', cr)
            wf_service.trg_write(uid, 'purchase.order', engage.purchase_order_id.id, cr)
        #Il faut relire l'objet car une nouvelle donnée est apparue entre temps dans l'engagement, account_invoice_id
        for engage in self.browse(cr, uid, ids, context):    
            wf_service.trg_write(uid, 'account.invoice', engage.account_invoice_id.id, cr)
            wf_service.trg_validate(uid, 'account.invoice', engage.account_invoice_id.id, 'invoice_open', cr)
        if not engage.account_invoice_id.id:
                raise osv.except_osv('Erreur','Aucune facture OpenERP n\'est associée a l\'engagement, cela est nécessaire pour mettre a jour les lignes de budgets.')
            
        return True
    
    def open_stock_moves(self, cr, uid, ids, context=None):
        stock_ids = []
        for engage in self.browse(cr, uid, ids):
            lines = [x.id for x in engage.purchase_order_id.order_line]
            stock_ids.extend(self.pool.get("stock.move").search(cr, uid, [('purchase_line_id','in',lines)]))
        res_action = self.pool.get("ir.actions.act_window").for_xml_id(cr, uid, 'openstc_achat_stock','action_open_achat_stock_reception_picking_move', context)
        res_action.update({'domain':[('id','in',stock_ids)]})
        return res_action
    
    def real_invoice_attached(self, cr, uid, ids):
        #A mettre lorsque le client aura précisé le pattern du nom de fichier de ses factures fournisseurs
        """
        if isinstance(ids, list):
            ids = ids[0]
        po_id = self.read(cr, uid, ids, ['purchase_order_id'], context)
        attachment_ids = self.pool.get("ir.attachment").search(cr, uid, [('res_id','=',po_id),('res_model','=','purchase.order')])
        attachments = self.pool.get("ir.attachment").read(cr, uid, attachment_ids, ['id','datas_fname'])
        prog = re.compile("pattern_invoice")
        for attachment in attachments:
            if prog.search(attachment['datas_fname']):
                self.write(cr, uid, ids, {'invoice_ok':True})
                return True
        return False"""
        #Pour éviter boucle infinie
        if not isinstance(ids, list):
            ids = [ids]
        for engage in self.browse(cr, uid, ids):
            if not engage.invoice_ok:
                self.write(cr, uid, ids, {'invoice_ok':True, 'date_invoice_received':fields.date.context_today(self, cr, uid, None)})
        return True
    
    def real_reception_attached(self, cr, uid, ids):
        #A mettre lorsque le client aura précisé le pattern du nom de fichier de ses factures fournisseurs
        """
        if isinstance(ids, list):
            ids = ids[0]
        po_id = self.read(cr, uid, ids, ['purchase_order_id'], context)
        attachment_ids = self.pool.get("ir.attachment").search(cr, uid, [('res_id','=',po_id),('res_model','=','purchase.order')])
        attachments = self.pool.get("ir.attachment").read(cr, uid, attachment_ids, ['id','datas_fname'])
        prog = re.compile("pattern_reception")
        for attachment in attachments:
            if prog.search(attachment['datas_fname']):
                self.write(cr, uid, ids, {'invoice_ok':True})
                return True
        return False"""
        #Pour éviter boucle infinie
        if not isinstance(ids, list):
            ids = [ids]
        for engage in self.browse(cr, uid, ids):
            if not engage.reception_ok:
                self.write(cr, uid, ids, {'reception_ok':True})
        return True
    
    def terminate_engage(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state':'done'},context)
        return
    
    def unlink(self, cr, uid, ids, context=None):
        #Si on supprimer un engagement, on doit forcer les documents associés à en générer un autre
        #En principe, aucun engagement ne doit etre supprimé
        engages = self.browse(cr, uid, ids)
        for engage in engages:
            self.pool.get("purchase.order").write(cr, uid, engage.purchase_order_id.id, {'validation':'budget_to_check'}, context)
        return super(open_engagement, self).unlink(cr, uid, ids, context)
    
open_engagement()
    

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
        'tx_erosion_info': fields.float('Taux Erosion de votre Service', digits=(2,2), readonly=True),
        'dispo':fields.boolean('Budget OK',readonly=True),
        }
    
    _defaults = {
        'dispo': False,
        }
    
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
            #TODO: Intégrer le taux d'érosion d'un service
            return {'value':{'budget_dispo_info':res,'budget_dispo':res}}
        return {'value':{}}
    
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
            'po_ask_id':fields.many2one('purchase.order.ask', 'Marché'),
            'po_ask_date':fields.related('po_ask_id','date_order', string='Date Marché', type='date'),
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
        #Si un marché est renseigné, il faut forcer les prix unitaires aux valeurs négociées avec le fournisseur pour chaque produit
        #TOCHECK: Si un produit n'est pas dans le marché, permettre tout de même la commande ? Pour l'instant on considère que oui            
        po_id = super(purchase_order, self).create(cr, uid, vals, context)
        po = self.browse(cr, uid, po_id)
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
            super(purchase_order, self).write(cr, uid, [po_id], {'order_line':values})
            if warning:
                self.log(cr, uid, po_id, 'Les prix unitaires de certaines lignes de la commande %s ont été modifiés' (po.name))
        return po_id

    def write(self, cr, uid, ids, vals, context=None):
        #Si un marché est renseigné, il faut forcer les prix unitaires aux valeurs négociées avec le fournisseur pour chaque produit
        #TOCHECK: Si un produit n'est pas dans le marché, permettre tout de même la commande ? Pour l'instant on considère que oui            
        if not isinstance(ids, list):
            ids = [ids]
        super(purchase_order, self).write(cr, uid, ids, vals, context)
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
            #Commande "hors_marché"
            if not po.po_ask_id:
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
        for po in self.browse(cr, uid, ids):
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
        if not line_not_ok:
            self.write(cr, uid, ids, {'validation':'engagement_to_check'})
        return
    
    def open_engage(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
            po = self.browse(cr, uid, ids, context)
            if self.check_all_dispo(cr, uid, ids, context):
                #On vérifie si on a un budget suffisant pour chaque ligne d'achat
                #On gère aussi le cas de plusieurs lignes référants au même compte analytique
                if not po.engage_id:
                    """po_values = {}
                    po_values.update({'validation':'done'})"""
                    """#Vérif montant, si > 300€, nécessite validation DST et élu
                    if not self.check_achat(cr, uid, ids, context):
                        po_values.update({'validation':'engagement_to_check'})"""
                    service_id = po.service_id
                    context.update({'user_id':uid,'service_id':service_id.id})
                    #Création de l'engagement et mise à jour des comptes analytiques des lignes de commandes (pour celles ou rien n'est renseigné
                    res_id = self.pool.get("open.engagement").create(cr, uid, {'user_id':uid,
                                                                               'service_id':service_id.id,
                                                                               'purchase_order_id':ids}, context)
                    """po_values.update({'engage_id':res_id})
                    self.write(cr, uid, ids, po_values, context=context)"""
                else:
                    res_id = po.engage_id.id
                return {
                    'type':'ir.actions.act_window',
                    'target':'new',
                    'res_model':'open.engagement',
                    'view_mode':'form',
                    'res_id':res_id
                    }
            else:
                self.write(cr, uid, ids, {'validation':'budget_to_check'}, context)
                self.pool.get("purchase.order.line").write(cr, uid, [x.id for x in po.order_line], {'dispo':False})
            return
        
    def action_invoice_create(self, cr, uid, ids, context=None):
        inv_id = super(purchase_order, self).action_invoice_create(cr, uid, ids, context)
        for purchase in self.browse(cr, uid, ids, context):
            self.pool.get("open.engagement").write(cr, uid, purchase.engage_id.id, {'account_invoice_id':inv_id})
        return inv_id
        
purchase_order()

class stock_picking(osv.osv):
    _inherit = "stock.picking"
    _name = "stock.picking"
    
    _columns = {
        }
    
    def action_done(self, cr, uid, ids, context=None):
        engage_ids = []
        if not isinstance(ids, list):
            ids = [ids]
        for picking in self.browse(cr ,uid, ids, context):
            for move_id in picking.move_lines:
                engage_id = move_id.purchase_line_id.order_id.engage_id and move_id.purchase_line_id.order_id.engage_id.id or False
                if engage_id and not (engage_id in engage_ids):
                    engage_ids.append(engage_id)
        wf_service = netsvc.LocalService('workflow')
        for engage_id in engage_ids:
            wf_service.trg_validate(uid, 'open.engagement', engage_id, 'signal_received', cr)
        self.pool.get("open.engagement").write(cr, uid, engage_ids, {'reception_ok':True})
        return super(stock_picking, self).action_done(cr, uid, ids, context)
    
stock_picking()
    
class crossovered_budget(osv.osv):
    _inherit = "crossovered.budget"
    _name = "crossovered.budget"
    
    def _calc_amounts(self, cr, uid, ids,  field_name, args, context=None):
        res = {}
        for budget in self.browse(cr, uid, ids, context):
            pract = 0.0
            theo = 0.0
            planned = 0.0
            #Pour chaque budget, on ajoute les montants de toutes leurs lignes budgétaires
            for line in budget.crossovered_budget_line:
                pract += line.practical_amount
                theo += line.theoritical_amount
                planned += line.planned_amount
            res.update({budget.id:{'pract_amount':pract, 'theo_amount':theo, 'planned_amount':planned}})
        return res
    
    _columns = {
        'planned_amount':fields.function(_calc_amounts, method=True, multi = True, string="Montant Plannifié", type='float'),
        'pract_amount':fields.function(_calc_amounts, method=True, multi = True, string="Montant Pratique", type='float'),
        'theo_amount':fields.function(_calc_amounts, method=True, multi = True, string="Montant Théorique", type='float'),
        }
    
crossovered_budget()

class res_users(osv.osv):
    _inherit = "res.users"
    _name = "res.users"
    
    _columns = {
        'max_po_amount':fields.float('Montant max autorisé par Bon de Commande', digit=(4,2)),
        'max_total_amount':fields.float('Montant Annuel max', digit=(5,2)),
        }
    
res_users()


