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
import addons
from tools.translate import _
from ciril_template_files import template_ciril_txt_file_engagement
import logging

#Objet gérant une demande de prix selon les normes pour les collectivités (ex: demander à 3 fournisseurs différents mini)
class purchase_order_ask(osv.osv):
    AVAILABLE_ETAT_PO_ASK = [('draft','Brouillon'),('done','Devis Clos')]
    _name = "purchase.order.ask"
    
    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')
    
    def _custom_sequence(self, cr, uid, context):
        seq = self.pool.get("ir.sequence").next_by_code(cr, uid, 'po_ask.number',context)
        user = self.pool.get("res.users").browse(cr, uid, uid)
        prog = re.compile('[Oo]pen[a-zA-Z]{3}/[Mm]anager')
        service = None
        if 'service_id' in context:
            service = context['service_id']
#        for group in user.groups_id:
#            if prog.search(group.name):
#                if isinstance(user.service_ids, list) and not service:
#                    service = user.service_ids[0]
#                else:
        if service:
            service = self.pool.get("openstc.service").browse(cr, uid, service)
            seq = seq.replace('xxx',self.remove_accents(service.name[:3]).upper())
        return seq
    
    _columns = {
        'order_lines':fields.one2many('purchase.order.ask.line','po_ask_id'),
        'name':fields.char('Objet de l\'achat',size=64),
        'sequence':fields.char('Numéro Devis',size=32, required=True),
        'state':fields.selection(AVAILABLE_ETAT_PO_ASK,'Etat', readonly=True),
        'suppliers_id':fields.one2many('purchase.order.ask.partners','po_ask_id','Fournisseurs potentiels'),
        'purchase_order_id':fields.many2one('purchase.order','Commande associée'),
        'date_order':fields.date('Date du Devis', required=True),
        'user_id':fields.many2one('res.users','Utilisateur Demandeur', readonly=True),
        'service_id':fields.many2one('openstc.service','Service Demandeur',required=True),
    }
    _defaults={
            'state':'draft',
            'sequence': lambda self,cr,uid,ctx={}: self._custom_sequence(cr, uid, ctx),
            'date_order':lambda self, cr, uid, context: fields.date.context_today(self ,cr ,uid ,context),
            'user_id':lambda self, cr, uid, context: uid,
            'service_id': lambda self, cr, uid, context: self.pool.get("res.users").browse(cr, uid, uid, context).service_ids[0].id,
    }
    
    
    def _create_report_attach(self, cr, uid, record, context=None):
        #sources inspired by _edi_generate_report_attachment of EDIMIXIN module
        ir_actions_report = self.pool.get('ir.actions.report.xml')
        matching_reports = ir_actions_report.search(cr, uid, [('model','=',self._name),
                                                              ('report_type','=','pdf')])
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
            except Exception:
                logging.getLogger('openerp').warning('purchase.order.ask report not generated, you passed those parameters : %s' % {'cr':cr, 'uid':uid, 'record':record, 'context':context} )
                
            
        return ret

    
    def constraints_to_draft_po(self, cr, uid, ids, context=None):
        suppliers_selected = 0
        line_errors = []
        for ask in self.browse(cr, uid, ids, context=context):
            if not ask.suppliers_id:
                raise osv.except_osv(_('Error'),_('You must supply at least one supplier before sending mail'))
            for partner_line in ask.suppliers_id:
                if partner_line.selected:
                    suppliers_selected += 1
            if suppliers_selected <> 1:
                raise osv.except_osv(_('Error'),_('You have to choose a supplier, and only one'))
            if not ask.order_lines:
                raise osv.except_osv(_('Error'),_('You must supply at least one order line before sending mail'))
            for line in ask.order_lines:
                if line.qte <= 0.0 or line.price_unit <= 0.0:
                    line_errors.append(line.id)
            
        if not line_errors:
            return True
        raise osv.except_osv(_('Error'),_('You must supply a positive quantity and price_unit'))
        return False
    
    def constraints_send_ask(self, cr, uid, ids, context=None):
        line_errors = []
        for ask in self.browse(cr, uid, ids, context=context):
            if ask.suppliers_id:
                if ask.order_lines:
                    for line in ask.order_lines:
                        if line.qte <= 0.0:
                            line_errors.append(line.id)
                else:
                    raise osv.except_osv(_('Error'),('You must supply at least one order line before sending mail'))
            else:
                raise osv.except_osv(_('Error'),_('You must supply at least one supplier before sending mail'))
        if not line_errors:
            return True
        raise osv.except_osv(_('Error'),_('You must supply a positive quantity'))
        return False
    
    def constraints_print_report(self, cr, uid, ids, context=None):
        line_errors = []
        for ask in self.browse(cr, uid, ids, context=context):
            if not ask.order_lines:
                raise osv.except_osv(_('Error'),_('You must supply at least one order line before sending mail'))
            for line in ask.order_lines:
                if line.qte <= 0.0:
                    line_errors.append(line.id)
        if not line_errors:
            return True
        raise osv.except_osv(_('Error'),_('You must supply a positive quantity before printing pdf report'))
        return False

    
    #launch report if conditions are checked
    def print_report(self, cr, uid, ids, context=None):
        if self.constraints_print_report(cr, uid, ids, context=context):
            datas = {
                     'ids':ids,
                     'model':'purchase.order.ask',
                     'form':{}}
            return {'type':'ir.actions.report.xml',
                    'report_name':'purchase.order.ask',
                    'datas':datas,
                    }
        return {'type':'ir.actions.act_window.close'}
    
    #create report, attach it and send mail with it to each supplier if conditions are checked
    def send_ask(self, cr, uid, ids, context=None):
        if self.constraints_send_ask(cr, uid, ids, context=context):
            #Envoi d'un mail aux fournisseurs potentiels
            #Puis on passe à l'étape d'après
            ask_lines = []
            ask_partners = []
            for ask in self.browse(cr, uid, ids):
                ir_attach_id = self._create_report_attach(cr, uid, ask, context)
                mail_values = {}
                mail_ids = []
                if ir_attach_id:
                    mail_values.update({'attachment_ids':[(4,ir_attach_id)]})
                #{'email_to':supplier_line.partner_address_id.email}
                supplier_lines_states = {'nothing':[],'error_mail':[],'mail':[]}
                for supplier_line in ask.suppliers_id:
                    ask_partners.append(supplier_line.id)
                    if not supplier_line.partner_id.opt_out and supplier_line.partner_address_id:
                        mail_values.update({'email_to':supplier_line.partner_address_id.email})
                        #pour chaque partner, on envoi un mail à son adresse mail
                        email_template_id = self.pool.get("email.template").search(cr, uid, [('model','=',self._name)])
                        mail_id = self.pool.get("email.template").send_mail(cr, uid, email_template_id[0], ids[0], force_send=False, context=context)
                        mail_ids.append(mail_id)
                        self.pool.get("mail.message").write(cr, uid, [mail_id], mail_values,context=context)
                        self.pool.get("mail.message").send(cr, uid, [mail_id], context)
                        #get if mail is correctly sent or not
                        if self.pool.get("mail.message").browse(cr, uid, mail_id, context).state == 'exception':
                            supplier_lines_states['error_mail'].append(supplier_line.id)
                        else:
                            supplier_lines_states['mail'].append(supplier_line.id)
                    else:
                        supplier_lines_states['nothing'].append(supplier_line.id)
                ask_lines.extend([x.id for x in ask.order_lines])
            
            #write notif_states for each supplier line
            #supplier_lines_states['mail'].append(supplier_line.id)
            ask_partners_obj = self.pool.get("purchase.order.ask.partners")
            for key, value in supplier_lines_states.items():
                if value:
                    ask_partners_obj.write(cr, uid, value, {'notif_state':key})


        return {'ir.actions.act_window.close'}
    
    #create purchase_order if conditions are checked    
    def to_draft_po(self, cr, uid, ids, context={}):
        if self.constraints_to_draft_po(cr, uid, ids, context=context):
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
                    raise osv.except_osv(_('Error'),_('Price units of somes products are missing'))
                list_prod.append({'prod_id':line.product_id.id,'price_unit':line.price_unit,'qte':line.qte, 'description':line.description, 'merge_line_ids':[(4,x.id) for x in line.merge_line_ids]})    
            partner_infos = self.pool.get("purchase.order").onchange_partner_id(cr, uid, [], supplier_id)['value']
            prod_actions = []
            pol_obj = self.pool.get("purchase.order.line")
            for prod_ctx in list_prod:
                prod_values = pol_obj.onchange_product_id(cr, uid, [], partner_infos['pricelist_id'], prod_ctx['prod_id'], prod_ctx['qte'],
                                                           False, supplier_id, price_unit=prod_ctx['price_unit'],
                                                           date_order=fields.date.context_today(self,cr,uid,context), context=context)['value']
                if 'taxes_id' in prod_values:
                    prod_values.update({'taxes_id':[(4,x) for x in prod_values['taxes_id']]})
                prod_values.update({'price_unit':prod_ctx['price_unit'], 
                                    'product_id':prod_ctx['prod_id'], 
                                    'merge_line_ids':prod_ctx['merge_line_ids']})
                if prod_ctx['description']:
                    prod_values.update({'name':prod_ctx['description']})
                prod_actions.append((0,0,prod_values))
            entrepot_id = self.pool.get("stock.warehouse").search(cr, uid, [])
            if not entrepot_id:
                raise osv.except_osv(_('Error'),_('You have to configure a warehouse'))
            if isinstance(entrepot_id, list):
                entrepot_id = entrepot_id[0]
            entrepot_infos = self.pool.get("purchase.order").onchange_warehouse_id(cr, uid, [], entrepot_id)['value']
            ret = {'service_id':ask.service_id.id, 'partner_id':supplier_id, 'po_ask_id':ask.id,'warehouse_id':entrepot_id,'order_line':prod_actions, 'description':ask.name}
            ret.update(partner_infos)
            ret.update(entrepot_infos)
            context.update({'from_ask':'1','service_id':ask.service_id.id})
            po_id = self.pool.get("purchase.order").create(cr, uid, ret, context)
            if po_id:
                ask.write({'state':'done'})
            return {
                'view_mode':'form',
                'target':'current',
                'type':'ir.actions.act_window',
                'res_model':'purchase.order',
                'res_id':po_id
                }
        return {'type':'ir.actions.act_window.close'}   
       
    def name_get(self, cr, uid, ids, context=None):
        res = []
        for ask in self.read(cr, uid, ids,['id', 'name','sequence']):
            res.append((ask['id'], '%s:%s' % (ask['sequence'], ask['name'])))
        return res
    
    def create(self, cr, uid, vals, context=None):
       if 'service_id' in vals:
           service = self.pool.get("openstc.service").browse(cr, uid, vals['service_id'], context=context)
           vals['sequence'] = vals['sequence'].replace('xxx',self.remove_accents(service.name[:3]).upper())
       return super(purchase_order_ask,self).create(cr, uid, vals, context=context)

purchase_order_ask()

class purchase_order_ask_line(osv.osv):
    _name = "purchase.order.ask.line"
    _columns = {
        'po_ask_id': fields.many2one('purchase.order.ask','Demande associée'),
        'product_id' : fields.many2one('product.product','Produit', required=True),
        'qte':fields.integer('Quantitié', required=True),
        'price_unit':fields.float('Prix Unitaire convenu',digit=(3,2)),
        'description':fields.char('Description',size=256),
        'infos':fields.char('Infos Supplémentaires',size=256),
        'date_order':fields.date('Date Souhaitée'),
        'merge_line_ids':fields.one2many('openstc.merge.line.ask', 'po_ask_line_id','Besoins Associés'),
        'state':fields.selection([('draft','Brouillon'),('waiting_pu','Attente PU'),('done','Terminé')], 'Etat',invisible=True)
        }
    
    _defaults = {
        'state':'draft',
        'date_order':lambda self,cr,uid,context: fields.date.context_today(self, cr, uid, context=context),
        }
    
    def onchange_product_id(self, cr, uid, ids, product_id=False):
        ret = {}
        if product_id:
            prod = self.pool.get("product.product").browse(cr, uid, product_id)
            ret.update({'description':prod.name_template})
        else:
            ret.update({'description':''})
        return {'value':ret}
                                                                  
    
purchase_order_ask_line()


class purchase_order_ask_partners(osv.osv):
    
    _AVAILABLE_NOTIF_STATES = [('nothing','Non notifié'),('error_mail','Non notifié(erreur envoi de mail)'),('mail','Mail Envoyé')]
    
    _name = "purchase.order.ask.partners"
    _columns = {
            'po_ask_id':fields.many2one('purchase.order.ask', 'Demande associée'),
            'partner_id':fields.many2one('res.partner','Fournisseur', required=True),
            'partner_address_id':fields.many2one('res.partner.address','Contact'),
            'selected':fields.boolean('Choisir ce fournisseur'),
            'state':fields.selection([('draft','Brouillon'),('waiting_selection','En Attente Sélection'),('done','Terminé')],
                                 'Etat',readonly=True, invisible=True),
            'notif_state':fields.selection(_AVAILABLE_NOTIF_STATES ,'Notification'),
            }
    _defaults = {
            'state':'draft'
    }
    
purchase_order_ask_partners()

##engage number model : YYYY-SER-xxx (YYYY: année, SER: service name on 3 characters, xxx: number increment )
#class open_engagement(osv.osv):
#
#    
#    _AVAILABLE_STATE_ENGAGE = [('draft','Brouillon'),('to_validate','A Valider'),('waiting_invoice','Attente Facture Fournisseur')
#                               ,('waiting_reception','Attente Réception Produits et Facture Fournisseur incluse'),('engage_to_terminate','Tous les Produits sont réceptionnés'),
#                               ('waiting_invoice_validated','Attente Facture Fournisseur Validée par Acheteur'),('except_invoice','Refus pour Paiement'),
#                               ('done','Clos'),('except_check','Engagement Refusé')]
#    _name="open.engagement"
#    _columns = {
#        'state':fields.selection(_AVAILABLE_STATE_ENGAGE, 'Etat', readonly=True),
#
#        }
#    _defaults = {
#
#            }
#
#    
#open_engagement()
    
class open_engagement_line(osv.osv):
    
    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')
    
    def _custom_sequence(self, cr, uid, context):
        seq = self.pool.get("ir.sequence").next_by_code(cr, uid, 'engage.number',context)
        user = self.pool.get("res.users").browse(cr, uid, uid)
        prog = re.compile('[Oo]pen[a-zA-Z]{3}/[Mm]anager')
        service = None
        if 'service_id' in context:
            service_id = context['service_id']
            service = self.pool.get("openstc.service").browse(cr, uid, service_id,context)
        else:
            for group in user.groups_id:
                if prog.search(group.name):
                    if isinstance(user.service_ids, list) and not service:
                        service = user.service_ids[0]
        if service:
            seq = seq.replace('-xxx-','-' + self.remove_accents(service.name[:3]).upper() + '-')
                
        return seq
    
    def _calc_amount(self, cr, uid, ids, field_name, arg=None, context=None):
        ret = {}
        for line in self.browse(cr, uid, ids, context):
            for po_line in line.order_line:
                """ret.setdefault(line.id,0.0)
                ret[line.id] += po_line.price_subtotal"""
                
                ret.setdefault(line.id,0.0)
                amount = po_line.price_subtotal
                for c in self.pool.get('account.tax').compute_all(cr, uid, po_line.taxes_id, po_line.price_unit, po_line.product_qty, po_line.order_id.partner_address_id.id, po_line.product_id.id, po_line.order_id.partner_id)['taxes']:
                    amount += c.get('amount', 0.0)
                ret[line.id] += amount
                
        return ret
    
    def _get_engage_ids(self, cr, uid, ids, context=None):
        ret = []
        for po in self.browse(cr, uid, ids, context):
            ret.extend([x.id for x in po.engage_lines])
        return ret
    
    _name = "open.engagement.line"
    _columns = {
        'name':fields.char('Numéro d\'Engagement',size=32, required=True),
        'order_line':fields.one2many('purchase.order.line','engage_line_id',string='Lignes d\'achats associées'),
        'amount':fields.function(_calc_amount,type='float',string='Montant de l\'Engagement', store={'purchase.order':[_get_engage_ids,['order_line'],9],'open.engagement.line':[lambda self,cr,uid,ids,context={}:ids,['order_line'],8]}),
        #'account_analytic_id':fields.related('order_line','account_analytic_id',string='Ligne Budgétaire Engagée', type='many2one', relation="account.analytic.account",store=True),
        'budget_line_id':fields.related('order_line','budget_line_id',string='Ligne Budgétaire Engagée', type='many2one', relation="crossovered.budget.lines",store=True),
        'engage_id':fields.many2one('purchase.order','Linked purchase'),
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
                assert move.product_id.id == merge.product_id.id, _('Erreur, stock move associated to merge lines does not rely to same product')
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
                assert move.product_id.id == merge.product_id.id, 'Error, stock moves doesn\'t match same products as merge lines'
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
                assert item['qty'] <= qty_available, 'Error, you try to supply a qty of products bigger than qty available in stock'
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
                raise osv.except_osv(_('Error'), _('you can\'t satisfy this need because stock product qty is null, make a delivering ask or wait for one.'))
                #raise osv.except_osv(_('Error'), _('Vous ne pouvez pas répondre A ce besoin car la quantité en stock de cette fourniture est nul, procédez A une Réappro ou attendez q\'une Réappro soit faite'))
            #qty needed to response to the ask, we could have already done a partial delivering 
            qty_to_deliver = merge.product_qty - merge.qty_delivered
            #if user selected more than one ask, raise an exception if qty total desired of a product < qty_available of this product
            if multiple_ids:
                if merge.product_id.id in prod_qty_deliver:
                    prod_qty_deliver[merge.product_id.id] += qty_to_deliver
                else:
                    prod_qty_deliver.update({merge.product_id.id:qty_to_deliver})
                if prod_qty_deliver[merge.product_id.id] > qty_available:
                    raise osv.except_osv(_('Error'), _('stock of the product %s is unavailable to stafisfy this need'))
                    #raise osv.except_osv(_('Erreur'),_('Les stocks du produit %s sont insuffisants pour répondre A une partie des besoins que vous avez sélectionnés.') %(merge.product_id.name))
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
        po_ids = []
        if not isinstance(ids, list):
            ids = [ids]
        for picking in self.browse(cr ,uid, ids, context):
            for move_id in picking.move_lines:
                engage_id = move_id.purchase_line_id and move_id.purchase_line_id.order_id and move_id.purchase_line_id.order_id.id or False
                if engage_id and not (engage_id in po_ids):
                    po_ids.append(engage_id)
#        wf_service = netsvc.LocalService('workflow')
#        #On vérifie que toutes les réceptions de produits sont faites
#        #for engage_id in engage_ids:
#            #wf_service.trg_validate(uid, 'open.engagement', engage_id, 'signal_received', cr)
        self.pool.get("purchase.order").write(cr, uid, po_ids, {'reception_ok':True}, context=context)    
        return super(stock_picking, self).action_done(cr, uid, ids, context)
    
stock_picking()

class stock_move(osv.osv):
    _inherit = "stock.move"
    _name = "stock.move"
    _columns = {
            'merge_ask_id':fields.many2one('openstc.merge.line.ask','Besoin Associé'),
        }
    
stock_move()




    
class product_product(osv.osv):
    _inherit = "product.product"
    _name = "product.product"
    
    def return_type_prod_values(self, cr, uid, context=None):
        ret = super(product_product, self).return_type_prod_values(cr, uid, context)
        #ret.extend([('fourniture','Fourniture Achetable')])
        return ret
    
    _columns = {    
        }

    #TOREMOVE ?
    def search(self, cr, uid, args, offset=0, limit=None, order=None, context=None, count=False):
        if context and 'force_product_uom' in context:
            args.extend([('isroom','=',False),('active','=',True)])
        return super(product_product, self).search(cr, uid, args, offset, limit, order, context, count)

product_product()



#Override in order to switch to engage if the user clicked on "Voir Produits A Réceptionnés" of this engage
class stock_partial_move(osv.osv_memory):
    _inherit = "stock.partial.move"
    _name = "stock.partial.move"
    _columns = {
        }
    
    def do_partial(self, cr, uid, ids, context=None):
        res = super(stock_partial_move, self).do_partial(cr, uid, ids, context)
        if 'old_active_ids' in context:
            #We put the original active_ids to keep the OpenERP mind (we just cheated the active_ids for this wizard)
            context.update({'active_ids':context['old_active_ids']})
            context.update({'active_model':context['old_active_model']})
            return {"type":"ir.actions.act_window_close"}
        return res
    
stock_partial_move()

#Override of openstc.service to add services linked with purchases
class openstc_service(osv.osv):
    _inherit = "openstc.service"
    _name = "openstc.service"
    
    def search(self, cr, uid, args=[], offset=0, limit=None, order=None, context=None, count=False):
        if context and context is not None:
            if 'only_my_services' in context:
                my_args = [('id','in',[x.id for x in self.pool.get("res.users").browse(cr,uid,uid,context=context).service_ids])]
                return super(openstc_service, self).search(cr, uid, args + my_args, offset=offset, limit=limit, order=order, context=context, count=count)
        return super(openstc_service, self).search(cr, uid, args, offset=offset, limit=limit, order=order, context=context, count=count)
    
    def onchange_code_serv_ciril(self, cr, uid, ids, code_serv_ciril=False,code=False):
        ret = {'value':{}}
        if code_serv_ciril and not code:
            ret['value'].update({'code':code_serv_ciril})
        return ret
    
    _columns = {
        'accountant_service':fields.selection([('cost','cost center'),('production','production center')],'Service comptable'),
        'code_serv_ciril':fields.char('Ciril Service Code',size=8, help="this field refer to service pkey from Ciril instance"),
        'code_function_ciril':fields.char('Ciril Function Code',size=8, help="this field refer to function pkey from Ciril instance"),
        'code_gest_ciril':fields.char('Ciril Gestionnaire Code',size=8, help="this field refer to gestionnaire pkey from Ciril instance"),
        #'purchase_order_ids':fields.one2many('purchase.order','service_id','Purchases made by this service'),
        #'purchase_order_ask_ids':fields.one2many('purchase.order.ask','service_id','Purchase Asks made by this service'),
        }
    
openstc_service()
    
