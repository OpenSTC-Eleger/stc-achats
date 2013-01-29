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
import time
import re
import base64
import unicodedata
import netsvc
#Objet gérant une demande de prix selon les normes pour les collectivités (ex: demander à 3 fournisseurs différents mini)
class purchase_order_ask(osv.osv):
    AVAILABLE_ETAT_PO_ASK = [('draft','Brouillon'),('waiting_supplier','Attente Choix du Fournisseur'),
                             ('waiting_purchase_order','Bon pour création de Commandes'),('done','Marché Clos')]
    _name = "purchase.order.ask"
    
    _columns = {
        'order_lines':fields.one2many('purchase.order.ask.line','po_ask_id'),
        'name':fields.char('Nom',size=64),
        'sequence':fields.char('Numéro Marché',size=4, required=True),
        'state':fields.selection(AVAILABLE_ETAT_PO_ASK,'Etat', readonly=True),
        'suppliers_id':fields.one2many('purchase.order.ask.partners','po_ask_id','Fournisseurs potentiels'),
        'purchase_order_id':fields.many2one('purchase.order','Commande associée'),
        'date_order':fields.date('Date d\'Obtention du Marché', required=True),
        'user_id':fields.many2one('res.users','Utilisateur Demandeur', readonly=True),
        'service_id':fields.many2one('openstc.service','Service Demandeur',required=True),
    }
    _defaults={
            'state':'draft',
            'sequence': lambda self, cr, uid, context: self.pool.get("ir.sequence").next_by_code(cr, uid, 'marche.po.number',context),
            'date_order':lambda self, cr, uid, context: fields.date.context_today(self ,cr ,uid ,context),
            'user_id':lambda self, cr, uid, context: uid,
            'service_id': lambda self, cr, uid, context: self.pool.get("res.users").browse(cr, uid, uid, context).service_ids[0].id,
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
            list_prod.append({'prod_id':line.product_id.id,'price_unit':line.price_unit,'qte':line.qte, 'merge_line_ids':[(4,x.id) for x in line.merge_line_ids]})    
        partner_infos = self.pool.get("purchase.order").onchange_partner_id(cr, uid, [], supplier_id)['value']
        prod_actions = []
        pol_obj = self.pool.get("purchase.order.line")
        for prod_ctx in list_prod:
            prod_values = pol_obj.onchange_product_id(cr, uid, [], partner_infos['pricelist_id'], prod_ctx['prod_id'], prod_ctx['qte'],
                                                       False, supplier_id, price_unit=prod_ctx['price_unit'],
                                                       date_order=fields.date.context_today(self,cr,uid,context), context=context)['value']
            prod_values.update({'price_unit':prod_ctx['price_unit'], 'product_id':prod_ctx['prod_id'], 'merge_line_ids':prod_ctx['merge_line_ids']})
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
        'merge_line_ids':fields.one2many('openstc.merge.line.ask', 'po_ask_line_id','Besoins Associés'),
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
                               ('done','Clos'),('except_check','Engagement Refusé')]
    _name="open.engagement"
    #TODO: Voir si un fields.reference pourrait fonctionner pour les documents associés a l'engagement (o2m de plusieurs models)
    _columns = {
        'name':fields.char('Numéro Bon  d\'Engagement', size=16, required=True),
        'description':fields.related('purchase_order_id', 'description', string='Objet de l\'achat', type="char"),
        'service_id':fields.many2one('openstc.service','Service Demandeur', required=True),
        'user_id':fields.many2one('res.users', 'Personnel Engagé', required=True),
        'purchase_order_id':fields.many2one('purchase.order','Commande associée'),
        'account_invoice_id':fields.many2one('account.invoice','Facture (OpenERP) associée'),
        'check_dst':fields.boolean('Signature DST'),
        #'date_invoice_received':fields.date('Date Réception Facture'),
        'date_engage_validated':fields.date('Date de Validation du Bon d\'Engagement', readonly=True),
        'date_engage_done':fields.datetime('Date de Cloture de l\'engagement',readonly=True),
        'state':fields.selection(_AVAILABLE_STATE_ENGAGE, 'Etat', readonly=True),
        'reception_ok':fields.boolean('Tous les Produits sont réceptionnés', readonly=True),
        'invoice_ok':fields.boolean('Facture Founisseur Jointe', readonly=True),
        'justificatif_refus':fields.text('Justification de votre Refus pour Paiement'),
        'attach_ids':fields.function(_get_engage_attaches, type='one2many', relation='ir.attachment',string='Documents Joints'),
        'engage_lines':fields.one2many('open.engagement.line','engage_id',string='Numéros d\'Engagements'),
        'supplier_id':fields.related('purchase_order_id','partner_id', string='Fournisseur', type='many2one', relation='res.partner'),
        'justif_check':fields.text('Justification de la décision de l\'Elu',state={'invisible':['|',('check_dst','=',False),('state','=','to_validate')],
                                                                         'readonly':[('check_dst','=',True)]}),
        'procuration_dst':fields.boolean('Procuration DST ?',readonly=True),
        'id':fields.integer('Id'),
        'current_url':fields.char('URL Courante',size=256),
        }
    _defaults = {
            'name':lambda self,cr,uid,context:self.pool.get("ir.sequence").next_by_code(cr, uid, 'open.engagement',context),
            'state':'draft',
            'user_id':lambda self,cr,uid,context:uid,
            'procuration_dst': lambda *a: 0,
            }
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
    
    def _create_report_attach(self, cr, uid, record, context=None):
        #sources insipered by _edi_generate_report_attachment of EDIMIXIN module
        ir_actions_report = self.pool.get('ir.actions.report.xml')
        matching_reports = ir_actions_report.search(cr, uid, [('model','=',self._name),
                                                              ('report_type','=','jasper')])
        ret = False
        if matching_reports:
            report = ir_actions_report.browse(cr, uid, matching_reports[0])
            report_service = 'report.' + report.report_name
            service = netsvc.LocalService(report_service)
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
        return ret
    
    def check_achat(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        po_id = self.read(cr, uid, ids, ['purchase_order_id'])
        return self.pool.get("purchase.order").check_achat(cr, uid, po_id['purchase_order_id'][0], context)
    
    def check_elu(self, cr, uid, ids, context=None):
        po_ids = []
        if isinstance(ids, list):
            ids = ids[0]
        engage = self.browse(cr, uid, ids)
        if not engage.check_dst:
            raise osv.except_osv('Erreur','Le DST doit avoir signé l\'engagement avant que vous ne puissiez le faire')
        po_ids.append(engage.purchase_order_id.id)
        self.pool.get("purchase.order").write(cr, uid, [engage.purchase_order_id.id], {'validation':'done'})
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(uid, 'open.engagement', engage.id, 'signal_validated', cr)
        return {
            'type':'ir.actions.act_window',
            'res_model':'open.engagement',
            'res_id':ids,
            'view_mode':'form',
            'view_type':'form',
            'target':'current',
            'context':{'service_id':engage.service_id.id}
            }
    
    def procuration_dst(self,cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'procuration_dst':True}, context=context)
        #TODO: faire un res.log au DST
        return {
            'type':'ir.actions.act_window',
            'res_model':'open.engagement',
            'res_id':ids[0],
            'view_mode':'form',
            'view_type':'form',
            'target':'current',
            }
    
    def link_engage_po(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state':'to_validate'}, context)
        for engage in self.browse(cr, uid, ids, context):
            self.pool.get("purchase.order").write(cr, uid, engage.purchase_order_id.id, {'engage_id':engage.id}, context)
        return True
    
    def validated_engage(self, cr, uid, ids, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        po_ids = [x.purchase_order_id.id for x in self.browse(cr, uid, ids, context)]
        #écriture des numéros d'engagement, un numéro par compte Analytique (et non par ligne d'achat)
        if not context:
            context = {}
        engage_obj = self.pool.get("open.engagement")
        #line_obj = self.pool.get("purchase.order.line")
        engage_line_obj = self.pool.get("open.engagement.line")
        account_amount = {}
        for engage in self.browse(cr, uid, ids, context):
            po = engage.purchase_order_id
            for line in po.order_line:
                #On vérifie si le compte Analytique est associé A un service technique
                if not line.account_analytic_id.service_id:
                    #On regroupe les montants par budget analytique
                    #TODO: Utiliser name_get si name ne rencoit pas le nom complet (cad avec le nom des comptes parents)
                    raise osv.except_osv('Erreur','Le compte Analytique %s n\'est associé A aucun service technique.' % line.account_analytic_id.name)
                account_amount.setdefault(line.account_analytic_id.id,{'line_id':[],'service_id':0})
                account_amount[line.account_analytic_id.id]['line_id'].append(line.id)
                account_amount[line.account_analytic_id.id]['service_id'] = line.account_analytic_id.service_id.id
            engage_line = []
            #On crée les numéros d'engagements associés
            for key, value in account_amount.items():
                context.update({'service_id':value['service_id']})
                #line_obj.write(cr, uid, value['line_id'], {'num_engage':engage_obj._custom_sequence(cr, uid, context)}, context=context)
                engage_line.append(engage_line_obj.create(cr, uid, {'order_line':[(4,x) for x in value['line_id']]}, context=context))
            #puis on associe les engage.lines crées A l'engagement en cours
            self.write(cr, uid, [engage.id], {'engage_lines':[(4,x) for x in engage_line], 'date_engage_validated':fields.date.context_today(self, cr, uid, context)}, context=context)
            self.pool.get("purchase.order").write(cr ,uid, po_ids, {'validation':'done'}, context=context)
            #force cursor commit to give up-to-date data to jasper report
            cr.commit()
            ret = self._create_report_attach(cr, uid, engage, context)
        return True
    
    def validate_po_invoice(self, cr, uid, ids,context=None):
        wf_service = netsvc.LocalService('workflow')
        if not isinstance(ids, list):
            ids = [ids]
        for engage in self.browse(cr, uid, ids, context):
            wf_service.trg_validate(engage.user_id.id, 'purchase.order', engage.purchase_order_id.id, 'purchase_confirm', cr)
            wf_service.trg_write(engage.user_id.id, 'purchase.order', engage.purchase_order_id.id, cr)
        #Il faut relire l'objet car une nouvelle donnée est apparue entre temps dans l'engagement, account_invoice_id
        for engage in self.browse(cr, uid, ids, context):    
            wf_service.trg_write(engage.user_id.id, 'account.invoice', engage.account_invoice_id.id, cr)
            wf_service.trg_validate(engage.user_id.id, 'account.invoice', engage.account_invoice_id.id, 'invoice_open', cr)
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
    
    def all_reception_done(self, cr, uid, ids):
        if isinstance(ids, list):
            ids = ids[0]
        #On vérifie que toutes le réceptions de produits sont faites
        engage_id = self.browse(cr, uid, ids)
        for line in engage_id.purchase_order_id.order_line:
            for move in line.move_ids:
                if move.state <> 'done':
                    return False
            #if not engage.reception_ok:
            #    self.write(cr, uid, ids, {'reception_ok':True})
        return True
    
    def engage_done(self, cr, uid, ids, context=None):
        engage = self.browse(cr, uid, ids[0], context)
        self.write(cr, uid, ids, {'state':'done','date_engage_done':datetime.now()})
        self.pool.get('ir.attachment').write(cr, uid, [x.id for x in engage.attach_ids], {'engage_done':True}, context=context)
        return True
    
    """def terminate_engage(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        attach = self.browse(cr, uid, ids, context)
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(uid, 'open.engagement', attach.res_id, 'terminate_engage', cr)
        return True"""
    
    def create(self, cr, uid, vals, context=None):
        res_id = super(open_engagement, self).create(cr, uid, vals, context)
        url = self.compute_current_url(cr, uid, res_id, context)
        self.write(cr, uid, [res_id], {'current_url':url}, context=context)
        return res_id
    
    def write(self, cr, uid, ids, vals, context=None):
        if 'check_dst' in vals and vals['check_dst']:
            #Envoi du mail A l'élu pour lui demande sa signature Apres signature du DST
            #TODO: Comment connaitre l'élu auquel envoyer la demande ?
            template_id = self.pool.get("email.template").search(cr, uid, [('model_id','=','open.engagement'),('name','like','%Elu%')], context=context)
            if isinstance(template_id, list):
                template_id = template_id[0]
            if isinstance(ids, list):
                ids = ids[0]
            msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, ids, force_send=True, context=context)
            if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
                del vals['check_dst']
                self.log(cr, uid, ids, 'Erreur, Echec d\'envoi du mail A l\'élu, votre signature n\'est pas prise en compte pour cette fois.')
        super(open_engagement,self).write(cr, uid, ids, vals, context=context)    
        return True
    
    def unlink(self, cr, uid, ids, context=None):
        #Si on supprimer un engagement, on doit forcer les documents associés à en générer un autre
        #En principe, aucun engagement ne doit etre supprimé
        engages = self.browse(cr, uid, ids)
        for engage in engages:
            self.pool.get("purchase.order").write(cr, uid, engage.purchase_order_id.id, {'validation':'budget_to_check'}, context)
        return super(open_engagement, self).unlink(cr, uid, ids, context)
    
open_engagement()
    
class open_engagement_line(osv.osv):
    
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
    
    def _calc_amount(self, cr, uid, ids, field_name, arg=None, context=None):
        ret = {}
        for line in self.browse(cr, uid, ids, context):
            for po_line in line.order_line:
                ret.setdefault(line.id,0.0)
                ret[line.id] += po_line.price_subtotal
        return ret
    
    def _get_engage_ids(self, cr, uid, ids, context=None):
        ret = []
        for engage in self.browse(cr, uid, ids, context):
            ret.extend([x.id for x in engage.engage_lines])
        return ret
    
    _name = "open.engagement.line"
    _columns = {
        'name':fields.char('Numéro d\'Engagement',size=32, required=True),
        'order_line':fields.one2many('purchase.order.line','engage_line_id',string='Lignes d\'achats associées'),
        'amount':fields.function(_calc_amount,type='float',string='Montant de l\'Engagement', store={'open.engagement':[_get_engage_ids,['purchase_order_id'],9],'open.engagement.line':[lambda self,cr,uid,ids,context={}:ids,['order_line'],8]}),
        'account_analytic_id':fields.related('order_line','account_analytic_id',string='Ligne Budgétaire Engagée', type='many2one', relation="account.analytic.account",store=True),
        'engage_id':fields.many2one('open.engagement','Engagement Associé'),
        }
    
    _defaults = {
        'name':lambda self,cr,uid,context:self._custom_sequence(cr, uid, context),
        }
    
open_engagement_line()
    
class openstc_ask_prod(osv.osv):
    _name = "openstc.ask.prod"
    
    _AVAILABLE_STATE_ASK = [('draft','Brouillon'),('confirmed','Confirmé par le Demandeur'),('waiting_validation','En Attente de Validation par les service concernés'),
                            ('in_progress','En cours de Traitement'),('done','Terminée'),('in_except','Commande Interrompue')]
    
    _columns = {
        'sequence':fields.char('Numéro de la Demande', size=16, required=True),
        'name':fields.char('Description de la Demande',size=128),
        'user_id':fields.many2one('res.users','Demandeur',required=True),
        'service_id':fields.many2one('openstc.service','Service Demandeur', required=True),
        'site_id':fields.many2one('openstc.site','Site Demandeur'),
        'date_order':fields.date('Date de la Demande', required=True),
        'merge_line_ask_id':fields.one2many('openstc.merge.line.ask','ask_prod_id','Besoins'),
        'state':fields.selection(_AVAILABLE_STATE_ASK, 'Etat',readonly=True),
        }
    
    _defaults = {
        'user_id':lambda self, cr, uid, context:uid,
        'date_order':lambda self, cr, uid, context: fields.date.context_today(self, cr, uid, context),
        'sequence': lambda self, cr, uid, context: self.pool.get("ir.sequence").next_by_code(cr, uid, 'openstc.ask.prod.number',context),
        'state':'draft',
        }
    
    def have_stock_manager(self, cr, uid, ids, context=None):
        #TODO:
        return False
    
    def all_merge_done(self, cr, uid, ids, context=None):
        for ask in self.browse(cr, uid, ids, context):
            for merge in ask.merge_line_ask_id:
                if not merge.merge_ask_done:
                    return False
        return True
    
    """#TOCHECK: Si une partie de la demande peut etre satisafaite, faisons-nous une livraison partielle ?
    def check_stock(self, cr, uid, ids, context=None):
        prod_qty = {}
        for ask in self.browse(cr, uid, ids, context):
            already_asked_prods = {}
            #On récupère les produits ainsi que leurs quantités demandées
            for merge in ask.merge_line_ask_id:
                prod_qty.update({merge.product_id.id:merge.product_qty})
                already_asked_prods.setdefault(merge.product_id.id,0)
            #On récupère le stock réel de chaque produit
            stock_prod = self.pool.get("product.product")._product_available(cr, uid, prod_qty.keys(), ['qty_available'])
            #On récupère toutes les demandes référant aux produits de la demande actuel
            cr.execute('''select line.product_id, sum(line.product_qty) as qty from openstc_ask_prod as ask, openstc_merge_line_ask as line
                        where  ask.id = line.ask_prod_id and ask.id not in %s and ask.state not in %s 
                        group by line.product_id''', (tuple(ids), ('draft','done','in_except')))
            for value in cr.fetchall():
                already_asked_prods.update({value[0]:value[1]})
            prod_not_dispo = []
            #Puis on vérifie la dispo de chaque produit en fct du stock et des autres demandes
            for prod_id, qty in prod_qty.iteritems():
                if stock_prod[prod_id]['qty_available'] < already_asked_prods[prod_id] + qty:
                    prod_not_dispo.append(prod_id)
            #On coche les lignes de la demande dont le produit est dispo de suite
            self.write(cr, uid, ids, {'merge_line_ask_id':[(1,x.id,{'dispo':True}) for x in ask.merge_line_ask_id if x.product_id.id not in prod_not_dispo]})
        return prod_qty and not prod_not_dispo or False"""
    
    def create(self, cr, uid, vals, context=None):
        context.update({'service_id':vals['service_id'],'site_id':vals['site_id']})
        ask_id = super(openstc_ask_prod, self).create(cr, uid, vals, context)
        ask = self.browse(cr, uid, ask_id, context)
        self.pool.get("openstc.merge.line.ask").write(cr, uid, [x.id for x in ask.merge_line_ask_id], 
                                                      {'service_id':ask.service_id and ask.service_id.id or False,
                                                       'site_id':ask.site_id and ask.site_id.id or False})
        return ask_id
    
    def write(self, cr, uid, ids, vals, context=None):
        super(openstc_ask_prod, self).write(cr, uid, ids, vals, context)
        if 'service_id' in vals or 'site_id' in vals:
            for ask in self.browse(cr, uid, ids, context):
                self.pool.get("openstc.merge.line.ask").write(cr, uid, [x.id for x in ask.merge_line_ask_id], {'service_id':ask.service_id.id,'site_id':ask.site_id.id})
        return True
    
    
"""    def _check_service_site(self, cr, uid, ids, context=None):
        for ask in self.browse(cr, uid, ids, context):
            if ask.service_id and ask.site_id \
             or not ask.service_id and not ask.site_id:
                return False
        return True

    _constraints = [(_check_service_site,'Erreur, Vous devez obligatoirement saisir soit un service soit un site et non les deux pour votre Demande.',['service_id','site_id'])]
    """
openstc_ask_prod()
    
class openstc_merge_line_ask(osv.osv):
    _name = "openstc.merge.line.ask"
    
    def _get_merge_ids(self, cr, uid, ids, context=None):
        return ids
    
    def _get_merge_by_prod_ids(self, cr, uid, ids, context=None):
        prod_ids = []
        #get all products concerned by a receive of another merge(s)
        for merge in self.browse(cr, uid ,ids, context):
            if merge.product_id and merge.product_id.id not in prod_ids:
                prod_ids.append(merge.product_id.id) 
        ret = self.search(cr, uid, [('product_id','in', prod_ids),('ask_prod_id','!=',False),('merge_ask_done','=',False)])
        return ret 
    
    def _calc_merge_ask_donable_done(self, cr, uid, ids,field_name, arg=None, context=None):
        ret =  {}
        for merge in self.browse(cr, uid, ids, context):
            qty_delivered = 0
            qty_available = merge.product_id.qty_available or 0.0
            for move in merge.stock_move_ids:
                #check if move and merge belong to the same product
                assert move.product_id.id == merge.product_id.id, 'Erreur, les mouvements de stocks associés au besoin ne correspondent pas au meme produit.'
                if move.state == 'done':
                    qty_delivered += move.product_qty
            ret.update({merge.id:{'qty_delivered':qty_delivered, 
                                  'merge_ask_donable':merge.product_qty - qty_delivered <= qty_available, 
                                  'merge_ask_done':merge.product_qty == qty_delivered,
                                  'qty_remaining':merge.product_qty - qty_delivered}})
        return ret
    
    
    def _get_moved_merge_ids(self, cr, uid, ids, context=None):
        ret = []
        for move in self.browse(cr, uid, ids, context):
            if move.merge_ask_id and not move.merge_ask_id in ret:
                ret.append(move.merge_ask_id.id)
        return ret
    
    def _get_qty_delivered(self, cr, uid, ids, field_name, args=None, context=None):
        ret = {}
        for merge in self.browse(cr, uid, ids, context):
            qty_delivered = 0
            for move in merge.stock_move_ids:
                #check if move and merge belong to the same product
                assert move.product_id.id == merge.product_id.id, 'Erreur, les mouvements de stocks associés au besoin ne correspondent pas au meme produit.'
                if move.state == 'done':
                    qty_delivered += move.product_qty
            ret.update({merge.id:qty_delivered})
        return ret
    
    #_AVAILABLE_STATE_PO = [('ras','RAS'),('waiting_purchase','Réappro en cours'),('purchase_to_receive','Réappro vous est livrable'),('purchase_receive_done','Livraison Réappro faite')]
    #_AVAILABLE_STATE_RECEIVE = [('ras','RAS'),('to_partial_receive','Livraison Partielle Possible'),('partial_receive_done','Livraison partielle Faite'),('to_receive','Besoin entiérement Livrable'),('receive_done','Besoin entiérement livré')]
    
    _columns = {
        'product_id':fields.many2one('product.product','Produit'),
        'product_qty':fields.float('Qté Désirée',required=True),
        'service_id':fields.many2one('openstc.service','Service Bénéficiaire'),
        'site_id':fields.many2one('openstc.site','Site Bénéficiaire'),
        'price_unit':fields.float('Prix Unitaire (remplie après facturation)',digit=(4,2)),
        'po_line_id':fields.many2one('purchase.order.line','Ligne Commande associée'),
        'move_line_id':fields.many2one('account.move.line','Move Line Associated'),
        'invoice_line_id':fields.many2one('account.invoice.line','Ligne Achat associée'),
        'ask_prod_id':fields.many2one('openstc.ask.prod','Demande de Fourniture Associée'),
        'po_ask_line_id':fields.many2one('purchase.order.ask.line', 'Ligne de Devis associée'),
        'dispo':fields.boolean('Disponible en Stock (Calculé A la saisie de la Demande)', readonly=True),
        'stock_move_ids':fields.one2many('stock.move','merge_ask_id','Mouvements de Stock Associés'),
        #'state_po':fields.selection(_AVAILABLE_STATE_PO, 'Etat de l\'approvisionnement', readonly=True),
        #'state_receive':fields.selection(_AVAILABLE_STATE_RECEIVE, 'Etat de la Livraison sur Stock', readonly=True),
        'qty_available':fields.related('product_id','qty_available',type='float',string="Qté Dispo En Stock"),
        'qty_delivered':fields.function(_calc_merge_ask_donable_done, multi='ask_done', type='float', store={'stock.move':(_get_moved_merge_ids, ['merge_ask_id'],10),'openstc.merge.line.ask':(_get_merge_ids,['product_qty','stock_move_ids'],8)}, string='Qté Livrée'),
        'qty_remaining':fields.function(_calc_merge_ask_donable_done, multi='ask_done', type='float', store={'stock.move':(_get_moved_merge_ids, ['merge_ask_id'],10),'openstc.merge.line.ask':(_get_merge_ids,['product_qty','stock_move_ids'],8)}, string='Qté Restante A Fournir'),
        'merge_ask_donable':fields.function(_calc_merge_ask_donable_done, multi='ask_done', type='boolean',string='Besoin Satisfaisable', store={'openstc.merge.line.ask':(_get_merge_by_prod_ids,['product_qty','qty_available'],10)}),
        'merge_ask_done':fields.function(_calc_merge_ask_donable_done, multi='ask_done', type='boolean',string='Besoin Satisfait', store={'stock.move':(_get_moved_merge_ids, ['merge_ask_id'],10),'openstc.merge.line.ask':(lambda self,cr,uid,ids,context={}:ids,['product_qty','stock_move_ids'],10)})
        }
    
    _order = "product_id,service_id,site_id"
    
    """
    @param ids: merge_ask ids
    @param vals : list of dicts containing prod_id, qte_to_deliver and merge_ask_id, used to create some stock.move
    @return: True
    """
    #TODO:
    def create_moves(self, cr, uid, vals, context=None):
        #create one move per list item
        prod_obj = self.pool.get("product.product")
        merge_obj = self.pool.get("openstc.merge.line.ask")
        move_obj = self.pool.get("stock.move")
        move_ids = []
        for item in vals:
            if ('prod_id' and 'merge_ask_id' and 'qty') in item:
                merge = merge_obj.browse(cr, uid, item['merge_ask_id'], context)
                prod = merge.product_id
                qty_available = prod.qty_available or 0.0
                #TODO: check if qty_deliver + qty already delivered <= merge.product_qty, otherwise raise an exception 
                assert item['qty'] <= qty_available, 'Erreur, Vous essayez de livrer une quantité de fourniture supérieure au stock disponible.'
                #move creation
                values = move_obj.onchange_product_id(cr, uid, [], prod_id=item['prod_id'])['value']
                values.update({'product_id':prod.id,'product_qty':item['qty']})
                move_id = move_obj.create(cr, uid, values, context=context)
                #force validation of stock move
                move_obj.action_done(cr, uid, [move_id], context)
                wf_service = netsvc.LocalService('workflow')
                wf_service.trg_write(uid, 'stock.move', move_id, cr)
                move_obj.write(cr, uid, [move_id], {'merge_ask_id':merge.id}, context=context)
        return True
    
    def create_po(self, cr, uid, ids, context=None):
        return
    
    # if multiple ids: generates stock_move, if qty_available < qte desired moves only qty_available, qte desired otherwise 
    def to_respond(self, cr, uid, ids, context=None): 
        multiple_ids = len(ids) >1
        prod_qty_deliver = {}
        values = []
        ask_ids = []
        for merge in self.browse(cr, uid, ids, context):
            qty_available = merge.product_id.qty_available or 0.0
            #TODO: we can filter with qty_virtual_available to know if some prods are planned to be received                
            if qty_available == 0.0: 
                raise osv.except_osv('Erreur', 'Vous ne pouvez pas répondre A ce besoin car la quantité en stock de cette fourniture est nul, procédez A une Réappro ou attendez q\'une Réappro soit faite')
            #qty needed to response to the ask, we could have already done a partial delivering 
            qty_to_deliver = merge.product_qty - merge.qty_delivered
            #if user selected more than one ask, raise an exception if qty total desired of a product < qty_available of this product
            if multiple_ids:
                if merge.product_id.id in prod_qty_deliver:
                    prod_qty_deliver[merge.product_id.id] += qty_to_deliver
                else:
                    prod_qty_deliver.update({merge.product_id.id:qty_to_deliver})
                if prod_qty_deliver[merge.product_id.id] > qty_available:
                    raise osv.except_osv('Erreur','Les stocks du produit %s sont insuffisants pour répondre A une partie des besoins que vous avez sélectionnés.' %(merge.product_id.name))
            #if user selected only one ask and qty_available < qty needed to terminate the ask, we do a partial delivering
            else:
                qty_to_deliver = min(qty_available, qty_to_deliver)
            values.append({'prod_id':merge.product_id.id,'merge_ask_id':merge.id,'qty':qty_to_deliver})
            #get ask_prod relying to those merge lines
            if merge.ask_prod_id and merge.ask_prod_id.id not in ask_ids:
                ask_ids.append(merge.ask_prod_id.id)
        if values:
            self.create_moves(cr, uid, values, context)    
        res_action = self.pool.get("ir.actions.act_window").for_xml_id(cr, uid, 'openstc_achat_stock','openstc_merge_line_ask_view', context)
        wf_service = netsvc.LocalService('workflow')
        for ask_id in ask_ids:
            wf_service.trg_validate(uid, 'openstc.ask.prod', ask_id, 'done', cr)
        return res_action

    #Action de Lancer une Réappro selon un Besoin
    #Note: ce sera aussi cette méthode qui sera appelée avec l'action liée A l'ir.value
    def to_do_purchase(self, cr, uid, ids, context=None):
        for merge in self.browse(cr, uid, ids, context):
            pass
        return

    def create(self, cr, uid, vals, context=None):
        if 'service_id' in context or 'site_id' in context:    
            vals.update({'service_id':context.get('service_id',False),'site_id':context.get('site_id',False)})
        return super(openstc_merge_line_ask, self).create(cr, uid, vals, context)
    
openstc_merge_line_ask()


class stock_picking(osv.osv):
    _inherit = "stock.picking"
    _name = "stock.picking"
    
    _columns = {
        }
    
    #TOCHECK: Vérifier si nécessiter de vérifier les stock.move, puisqu'apparemment action_done n'est appelée uniquement
    #lorsque tous les stock.move sont faits (Etat Done seulement, ou aussi en exception ?)
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
        #On vérifie que toutes les réceptions de produits sont faites
        for engage_id in engage_ids:
            wf_service.trg_validate(uid, 'open.engagement', engage_id, 'signal_received', cr)
        #self.pool.get("open.engagement").write(cr, uid, engage_ids, {'reception_ok':True})
        return super(stock_picking, self).action_done(cr, uid, ids, context)
    
stock_picking()

class stock_move(osv.osv):
    _inherit = "stock.move"
    _name = "stock.move"
    _columns = {
            'merge_ask_id':fields.many2one('openstc.merge.line.ask','Besoin Associé'),
        }
    
stock_move()

class res_users(osv.osv):
    _inherit = "res.users"
    _name = "res.users"
    
    _columns = {
        'max_po_amount':fields.float('Montant par Bon de Commande', digit=(4,2), help="Montant Max autorisé par Bon de Commande"),
        'max_total_amount':fields.float('Montant Annuel max', digit=(5,2)),
        }
    
res_users()

class product_product(osv.osv):
    _inherit = "product.product"
    _name = "product.product"
    _columns = {
        }

    def search(self, cr, uid, args, offset=0, limit=None, order=None, context=None, count=False):
        if 'force_product_uom' in context:
            args.extend([('isroom','=',False),('active','=',True)])
        return super(product_product, self).search(cr, uid, args, offset, limit, order, context, count)

product_product()


class ir_attachment(osv.osv):
    _inherit = "ir.attachment"
    _name = "ir.attachment"
    _columns = {
        'state':fields.selection([('to_check','A Traiter'),('validated','Facture Validée'),
                                  ('refused','Facture Refusée'),('not_invoice','RAS'),('except_send_mail','Echec envoi du mail')], 'Etat', readonly=True),
         'action_date':fields.datetime('Date de la derniere action', readonly=True),
         'engage_done':fields.boolean('Engagement Clos',readonly=True),
         'attach_made_done':fields.boolean('Cette Facture Clos l\'engagement', readonly=True),
         'justif_refuse':fields.text('Justificatif Refus', state={'required':[('state','=','refused')], 'invisible':[('state','!=','refused')]})
        }
    
    _defaults = {
        'state':'not_invoice',
        }
    #Override to put an attach as a pdf invoice if it responds to the pattern 
    def create(self, cr, uid, vals, context=None):
        attach_id = super(ir_attachment, self).create(cr, uid, vals, context=context)
        attach = self.browse(cr, uid, attach_id, context)
        is_invoice = False
        #invoice : F-yyyy-MM-dd-001
        prog = re.compile('F-[1-2][0-9]{3}-[0-1][0-9]-[0-3][0-9]-[0-9]{3}')
        #if attach.res_model == 'open.engagement':
        is_invoice = prog.search(attach.datas_fname)
        if is_invoice:
            self.write(cr, uid, [attach_id], {'state':'to_check'}, context=context)
            #Envoye une notification A l'Acheteur pour lui signifier qu'il doit vérifier une facture
            engage = self.pool.get("open.engagement").browse(cr, uid, attach.res_id, context)
            self.log(cr, engage.user_id.id, attach_id,'Vous devez vérifier la facture %s ajoutée le %s sur votre engagement %s' %(attach.datas_fname,fields.date.context_today(self, cr, uid, context), engage.name))
        return attach_id
    
    def send_invoice_to_pay(self, cr, uid, ids, context=None):
        #ids refer to attachment that need to be sent with mail
        #Envoie de la piece jointe en mail au service compta
        if isinstance(ids, list):
            ids = ids[0]
        attach = self.browse(cr, uid, ids, context)
        template_id = self.pool.get("email.template").search(cr, uid, [('model_id','=','open.engagement'),('name','like','%Valid%')], context=context)
        if isinstance(template_id, list):
            template_id = template_id[0]
        msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, attach.res_id, force_send=False, context=context)
        self.pool.get("mail.message").write(cr, uid, [msg_id], {'attachment_ids':[(4, ids)]}, context=context)
        self.pool.get("mail.message").send(cr, uid, [msg_id], context)
        if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
            self.pool.get("open.engagement").log(cr, uid, attach.res_id, 'Erreur lors de l\'envoi du mail au service compta pour paiement de la facture %s'%(attach.datas_fname))
            self.write(cr, uid, [ids], {'state':'except_send_mail','action_date':datetime.now()}, context)
        else:
            self.write(cr, uid, [ids], {'state':'validated','action_date':datetime.now()}, context)
        
        return {'res_model':'open.engagement',
                'view_mode':'form,tree',
                'target':'current',
                'res_id':attach.res_id,
                'type':'ir.actions.act_window'
                }
    
    def action_refuse_invoice_to_pay(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        return {'type':'ir.actions.act_window',
                'res_model':'openstc.open.engage.refuse.inv.wizard',
                'view_mode':'form',
                'view_type':'form',
                'target':'new',
                'context':{'attach_id':ids}
                }
    
    def refuse_invoice_to_pay(self, cr, uid, ids, context=None):
        #ids refer to attachment that need to be sent with mail
        #Envoie de la piece jointe en mail au service compta
        if isinstance(ids, list):
            ids = ids[0]
        attach = self.browse(cr, uid, ids, context)
        template_id = self.pool.get("email.template").search(cr, uid, [('model_id','=','open.engagement'),('name','like','%Refus%')], context=context)
        if isinstance(template_id, list):
            template_id = template_id[0]
        msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, attach.res_id, force_send=False, context=context)
        self.pool.get("mail.message").write(cr, uid, [msg_id], {'attachment_ids':[(4, ids)]}, context=context)
        self.pool.get("mail.message").send(cr, uid, [msg_id], context)
        if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
            self.pool.get("open.engagement").log(cr, uid, attach.res_id, 'Erreur lors de l\'envoi du mail', context=context)
            self.write(cr, uid, [ids], {'state':'except_send_mail','action_date':datetime.now()}, context)
        else:
            self.write(cr, uid, [ids], {'state':'refused','action_date':datetime.now()}, context)
        return {'res_model':'open.engagement',
                'view_mode':'form,tree',
                'target':'current',
                'res_id':attach.res_id,
                'type':'ir.actions.act_window'
                }
    
    #Action du Boutton Permettant de Clore l'engagement
    #Bloque s'il reste des factures à valider (état 'to_check' ou 'except_send_mail'
    #TOCHECK: Faut-il envoyer un mail de confirmation au service compta etc... ?
    def engage_complete(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        #TOCHECK: Vérifier s'il ne faudrait pas mettre ces tests dans une condition de wkf (A place de real_invoice_attached()) 
        attach = self.browse(cr, uid, ids, context)
        attach_ids = self.search(cr, uid, [('res_id','=',attach.res_id),('res_model','=','open.engagement'),('state','in',('to_check','except_send_mail'))], context=context)
        if attach_ids:
            raise osv.except_osv('Erreur','Vous ne pouvez pas clore l\'engagement car il reste des factures à traiter')
        else:
            if self.pool.get("open.engagement").browse(cr, uid, attach.res_id, context).reception_ok:
                self.write(cr, uid, [attach.id], {'attach_made_done':True},context=context)
                wf_service = netsvc.LocalService('workflow')
                wf_service.trg_validate(uid, 'open.engagement', attach.res_id, 'terminate_engage', cr)
            else:
                raise osv.except_osv('Erreur','Vous ne pouvez pas clore l\'engagement car il reste des produits A Réceptionner (dans OpenERP)')
        return {'res_model':'open.engagement',
                'view_mode':'form,tree',
                'target':'current',
                'res_id':attach.res_id,
                'type':'ir.actions.act_window'
                }
    
ir_attachment()

    

