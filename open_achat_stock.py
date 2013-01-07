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
    
    def test(self, cr, uid, context=None):
        acc_ids = self.pool.get("account.analytic.account").search(cr, 12, [])
        acc = self.pool.get("account.analytic.account").read(cr, 12, acc_ids,[])
        return
    
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
    
    def _get_engage_attaches(self, cr, uid, ids, field_name, arg=None, context=None):
        #Récup des pièces jointes de po
        engage_to_po = {}
        for engage in self.browse(cr, uid, ids, context):
            engage_to_po.update({engage.purchase_order_id.id:engage.id})
        po_ids = engage_to_po.keys()
        cr.execute('''select a.id, a.res_id 
                    from ir_attachment as a 
                    where a.res_id in %s and a.res_model = %s
                    or res_id in %s and a.res_model = %s 
                    group by a.res_id, a.id
                    order by a.res_id''',(tuple(ids), self._name, tuple(po_ids),'purchase.order'))
        ret = {}
        search_ids = []
        search_ids.extend(ids)
        search_ids.extend(po_ids)
        for id in ids:
            ret.setdefault(id, [])
        for r in cr.fetchall():
            if r[1] in ids:
                #Soit il s'agit d'une piece jointe associée a l'engagement
                ret[r[1]].append(r[0])
            else:
                #Soit il s'agit d'une piece jointe associée au bon de commande associé a l'engagement
                ret[engage_to_po[r[1]]].append(r[0])
        return ret
    
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
        'attach_ids':fields.function(_get_engage_attaches, type='one2many', relation='ir.attachment',string='Documents Joints')
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
    
class openstc_merge_line_ask(osv.osv):
    _name = "openstc.merge.line.ask"
    _columns = {
        'product_id':fields.many2one('product.product','Produit'),
        'product_qty':fields.integer('Qté Désirée',required=True),
        'service_id':fields.many2one('openstc.service','Service Bénéficiaire'),
        'site_id':fields.many2one('openstc.site','Site Bénéficiaire'),
        'price_unit':fields.float('Prix Unitaire (remplie après facturation)',digit=(4,2)),
        'po_line_id':fields.many2one('purchase.order.line','Ligne Commande associée'),
        'move_line_id':fields.many2one('account.move.line','Move Line Associated'),
        'invoice_line_id':fields.many2one('account.invoice.line','Ligne Achat associée'),
        #'ask_prod_id':fields.many2one('openstc.ask.prod','Demande de Fourniture Associée'),        
        }
    #Renvoie True si service_id XOR site_id
    def _check_service_site(self, cr, uid, ids, context=None):
        for merge in self.browse(cr, uid, ids ,context):    
            return (merge.service_id and not merge.site_id) or (not merge.service_id and merge.site_id)
        return True
    
    _constraints=[(_check_service_site,'une demande de produit doit etre associée a un service ou un site, mais pas les deux en memes temps.',['service_id','product_id','site_id'])]

openstc_merge_line_ask()


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
    


class res_users(osv.osv):
    _inherit = "res.users"
    _name = "res.users"
    
    _columns = {
        'max_po_amount':fields.float('Montant max autorisé par Bon de Commande', digit=(4,2)),
        'max_total_amount':fields.float('Montant Annuel max', digit=(5,2)),
        }
    
res_users()


