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
            except:
                pass
            
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
    def to_draft_po(self, cr, uid, ids, context=None):
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

#engage number model : YYYY-SER-xxx (YYYY: année, SER: service name on 3 characters, xxx: number increment )
class open_engagement(osv.osv):
    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')
    
    def search(self, cr, uid, args=[],offset=0,limit=None, order=None,context=None, count=False):
        if context and context is not None:
            if 'only_engage_todo' in context:
                my_args = [('engage_to_treat','=',True)]
                return super(open_engagement, self).search(cr, uid, args + my_args, offset=offset, limit=limit, order=order,context=context,count=count)
        return super(open_engagement, self).search(cr, uid, args, offset=offset, limit=limit, order=order,context=context,count=count)
    
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
        cr.execute('''select a.id, a.res_id, a.state
                    from ir_attachment as a 
                    where a.res_id in %s and a.res_model = %s
                    or res_id in %s and a.res_model = %s 
                    group by a.res_id, a.id
                    order by a.create_date DESC''',(tuple(ids), self._name, tuple(po_ids),'purchase.order'))
        ret = {}
        search_ids = []
        search_ids.extend(ids)
        search_ids.extend(po_ids)
        for id in ids:
            ret.setdefault(id, {'attach_ids':[],'engage_to_treat':False})
        for r in cr.fetchall():
            if r[1] in ids:
                if not ret[r[1]]['engage_to_treat']:
                    ret[r[1]]['engage_to_treat'] = r[2] in ('engage_to_treat',('except_send_mail'))
                #Soit il s'agit d'une piece jointe associée a l'engagement
                ret[r[1]]['attach_ids'].append(r[0])
            else:
                #Soit il s'agit d'une piece jointe associée au bon de commande associé a l'engagement
                ret[engage_to_po[r[1]]]['attach_ids'].append(r[0])
                
        return ret
    
    def _search_engage_to_treat(self, cr, uid, obj, name, args, context={}):
        if not args:
            return []
        if args[0] == ('engage_to_treat','=',True):
            cr.execute("select res_id from ir_attachment where state in ('to_check','except_send_mail') and res_model = %s group by res_id;",(self._name,))
            return [('id','in',[x for x in cr.fetchall()])]
        return []
    
    _AVAILABLE_STATE_ENGAGE = [('draft','Brouillon'),('to_validate','A Valider'),('waiting_invoice','Attente Facture Fournisseur')
                               ,('waiting_reception','Attente Réception Produits et Facture Fournisseur incluse'),('engage_to_terminate','Tous les Produits sont réceptionnés'),
                               ('waiting_invoice_validated','Attente Facture Fournisseur Validée par Acheteur'),('except_invoice','Refus pour Paiement'),
                               ('done','Clos'),('except_check','Engagement Refusé')]
    _name="open.engagement"
    #TODO: Voir si un fields.reference pourrait fonctionner pour les documents associés a l'engagement (o2m de plusieurs models)
    _columns = {
        'name':fields.char('Numéro de Suivi de commande', size=16, required=True),
        'description':fields.related('purchase_order_id', 'description', string='Objet de l\'achat', type="char"),
        'service_id':fields.many2one('openstc.service','Service Demandeur', required=True),
        'user_id':fields.many2one('res.users', 'Acheteur', required=True),
        'purchase_order_id':fields.many2one('purchase.order','Commande associée'),
        'account_invoice_id':fields.many2one('account.invoice','Facture (OpenERP) associée'),
        'check_dst':fields.boolean('Signature DST'),
        #'date_invoice_received':fields.date('Date Réception Facture'),
        'date_engage_validated':fields.date('Date Validation de la commande', readonly=True),
        'date_engage_done':fields.datetime('Date de Cloture de la commande',readonly=True),
        'state':fields.selection(_AVAILABLE_STATE_ENGAGE, 'Etat', readonly=True),
        'reception_ok':fields.boolean('Tous les Produits sont réceptionnés', readonly=True),
        'invoice_ok':fields.boolean('Facture Founisseur Jointe', readonly=True),
        'justificatif_refus':fields.text('Justification de votre Refus pour Paiement'),
        'attach_ids':fields.function(_get_engage_attaches, multi="attaches", type='one2many', relation='ir.attachment',string='Documents Joints'),
        'engage_lines':fields.one2many('open.engagement.line','engage_id',string='Numéros d\'Engagements'),
        'supplier_id':fields.related('purchase_order_id','partner_id', string='Fournisseur', type='many2one', relation='res.partner'),
        'justif_check':fields.text('Justification de la décision de l\'Elu'),
        #attrs={'invisible':['|',('check_dst','=',False),('state','=','to_validate')],'readonly':[('check_dst','=',True)]}
        'justif_check_infos':fields.related('justif_check', type="text", string='Justification de la décision de l\'Elu', store=True),
        'procuration_dst':fields.boolean('Procuration DST ?',readonly=True),
        'id':fields.integer('Id'),
        'current_url':fields.char('URL Courante',size=256),
        'elu_id':fields.many2one('res.users','Elu Concerné', readonly=True),
        'attach_datas_sumup':fields.binary('Purchase Sum\'up'),
        'attach_datas_fname_sumup':fields.char('Purchase Sum\'up Filename', size=256),
        'engage_to_treat':fields.function(_get_engage_attaches, fnct_search=_search_engage_to_treat, multi="attaches", type='boolean', string='Engage to Treat', method=True),
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
    
    def test(self, cr, uid, context=None):
        print addons.get_module_path('openstc_achat_stock')
        #we can user tools.config['my_param'] where my_param is an option on the openerp-server.conf file
        #TODO: add a custom option on this file to add a directory where storing generated engages.txt files
        return
    
    def get_elu_attached(self, cr, uid, id, context=None):
        service_id = self.browse(cr, uid, id, context).service_id.id
        groups_id = self.pool.get("res.groups").search(cr, uid, [('name','like','%Elu%')], context=context)
        elu_id = self.pool.get("res.users").search(cr, uid, ['&',('service_ids','=',service_id),('groups_id','in',groups_id),('name','not like','%Admin')], context=context)
        return elu_id and elu_id[0] or False
    
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
            except:
                pass
            
        return ret
    
    def _create_report_sumup_attach(self, cr, uid, record, context=None):
        #sources inspired by _edi_generate_report_attachment of EDIMIXIN module
        ir_actions_report = self.pool.get('ir.actions.report.xml')
        matching_reports = ir_actions_report.search(cr, uid, [('model','=','purchase.order'),
                                                              ('report_type','=','pdf',),
                                                               ('report_name','=','purchase.order.sumup')])
        ret = False
        if matching_reports:
            report = ir_actions_report.browse(cr, uid, matching_reports[0])
            report_service = 'report.' + report.report_name
            service = netsvc.LocalService(report_service)
            try:
                (result, format) = service.create(cr, uid, [record.purchase_order_id.id], {'model': self._name}, context=context)
                eval_context = {'time': time, 'object': record.purchase_order_id}
                if not report.attachment or not eval(report.attachment, eval_context):
                    # no auto-saving of report as attachment, need to do it manually
                    result = base64.b64encode(result)
                    file_name = 'Sum_up_'
                    file_name += record.name_get()[0][1]
                    file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', file_name)
                    file_name += ".pdf"
                    ir_attachment = self.pool.get('ir.attachment').create(cr, uid, 
                                                                          {'name': file_name,
                                                                           'datas': result,
                                                                           'datas_fname': file_name,
                                                                           'res_model': 'purchase.order',
                                                                           'res_id': record.purchase_order_id.id},
                                                                          context=context)
                    record.write({'attach_datas_sumup':result,'attach_datas_fname_sumup':file_name}),
                    
                    ret = ir_attachment
            except:
                pass
            
        return ret
    
    def check_achat(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        po_id = self.read(cr, uid, ids, ['purchase_order_id'])
        return self.pool.get("purchase.order").check_achat(cr, uid, po_id['purchase_order_id'][0], context)
    
    def action_dst_check(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        #create sum'up report for elu
        engage = self.browse(cr, uid, ids, context=context)
        if ids:
            if engage.purchase_order_id:
                self._create_report_sumup_attach(cr, uid, engage, context)
        #Envoi du mail A l'élu pour lui demande sa signature Apres signature du DST
        template_id = self.pool.get("email.template").search(cr, uid, [('model_id','=','open.engagement'),('name','like','%Elu%')], context=context)
        if isinstance(template_id, list):
            template_id = template_id[0]
        msg_id = self.pool.get("email.template").send_mail(cr, uid, template_id, ids, force_send=True, context=context)
        if self.pool.get("mail.message").read(cr, uid, msg_id, ['state'], context)['state'] == 'exception':
            #self.log(cr, uid, ids, _('Error, fail to notify Elu by mail, your check is avoid for this time'))
            raise osv.except_osv(_('Error'),_('Error, fail to notify Elu by mail, your check is avoid for this time'))
            #return False
        engage.write({'check_dst':True})
        #return True
        return {'type':'ir.actions.act_window.close'}
    
    def check_elu(self, cr, uid, ids, context=None):
        po_ids = []
        if isinstance(ids, list):
            ids = ids[0]
        engage = self.browse(cr, uid, ids)
        if not engage.check_dst:
            raise osv.except_osv(_('Error'),_('DST have to check engage first'))
        po_ids.append(engage.purchase_order_id.id)
        self.pool.get("purchase.order").write(cr, uid, [engage.purchase_order_id.id], {'validation':'done'})
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(uid, 'open.engagement', engage.id, 'signal_validated', cr)
        wf_service.trg_write(uid, 'open.engagement',engage.id,cr)
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
        for engage in self.browse(cr, uid, ids, context):
            self.pool.get("purchase.order").write(cr, uid, engage.purchase_order_id.id, {'engage_id':engage.id}, context)
        return True
    
    def to_validated_engage(self, cr, uid, ids ,context=None):
        self.write(cr, uid, ids, {'state':'to_validate'}, context)
        for engage in self.browse(cr, uid, ids, context):
            self.write(cr, uid, engage.id,{'elu_id':self.get_elu_attached(cr, uid, engage.id, context)},context=context)
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
                    raise osv.except_osv(_('Error'),_('Analytic account %s has not any service associated') % line.account_analytic_id.name)
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
            #self.pool.get("purchase.order").write(cr ,uid, po_ids, {'validation':'done'}, context=context)
            #self.validate_po_invoice(cr, uid, ids, context)
            #force cursor commit to give up-to-date data to jasper report
            #cr.commit()
            #ret = self._create_report_attach(cr, uid, engage, context)
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
            raise osv.except_osv(_('Error'),_('An OpenERP Invoice associated to this engage is needed, can not update budgets without') % line.account_analytic_id.name)
#            #raise osv.except_osv(_('Erreur'),_('Aucune facture OpenERP n\'est associée a l\'engagement, cela est nécessaire pour mettre a jour les lignes de budgets.'))    
        return True
    
    def open_stock_moves(self, cr, uid, ids, context=None):
        stock_ids = []
        for engage in self.browse(cr, uid, ids):
            lines = [x.id for x in engage.purchase_order_id.order_line]
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

    def open_purchase(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        engage = self.browse(cr, uid, ids, context=context)
        if engage.purchase_order_id:
            return {
                'type':'ir.actions.act_window',
                'res_model':'purchase.order',
                'res_id':engage.purchase_order_id.id,
                'context':context,
                'target':'new',
                'view_mode':'form',
                }
        raise osv.except_osv(_('Error'), _('No purchase found for this engage, please create a new one'))
        return False
    
    def real_invoice_attached(self, cr, uid, ids):
        #A mettre lorsque le client aura précisé le pattern du nom de fichier de ses factures fournisseurs

        if not isinstance(ids, list):
            ids = [ids]
        for engage in self.browse(cr, uid, ids):
            if not engage.invoice_ok:
                self.write(cr, uid, ids, {'invoice_ok':True, 'date_invoice_received':fields.date.context_today(self, cr, uid, None)})
        return True
    
    def write_ciril_engage(self, cr, uid, ids, context=None):
        ret = ''
        template = template_ciril_txt_file_engagement()
        
        for engage in self.browse(cr, uid, ids ,context=context):
            ret += template.create_file(engage)
            #write content in an ir.attachment
            ret = base64.b64encode(ret)
            self.pool.get("ir.attachment").create(cr, uid, {'name':'engages.txt',
                                                            'datas_fname':'engages.txt',
                                                            'datas':ret,
                                                            'res_model':self._name,
                                                            'res_id':engage.id
                                                            })
        return {'type':'ir.actions.act_window_close'}
    
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
    
    def create(self, cr, uid, vals, context=None):
        res_id = super(open_engagement, self).create(cr, uid, vals, context)
        url = self.compute_current_url(cr, uid, res_id, context)
        self.write(cr, uid, [res_id], {'current_url':url}, context=context)
        return res_id
    
    def write(self, cr, uid, ids, vals, context=None):
#        if 'check_dst' in vals and vals['check_dst']:
#            if not self.action_dst_check(cr, uid, ids, context):
#                del vals['check_dst']
        super(open_engagement,self).write(cr, uid, ids, vals, context=context)    
        return True
    
    def unlink(self, cr, uid, ids, context=None):
        #if engage is deleted, we force other objects to generate another one
        #TODO: in production, engage deletion is forbidden
        engages = self.browse(cr, uid, ids)
        for engage in engages:
            self.pool.get("purchase.order").write(cr, uid, engage.purchase_order_id.id, {'validation':'budget_to_check','engage_id':False}, context)
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
        engage_ids = []
        if not isinstance(ids, list):
            ids = [ids]
        for picking in self.browse(cr ,uid, ids, context):
            for move_id in picking.move_lines:
                engage_id = move_id.purchase_line_id and move_id.purchase_line_id.order_id.engage_id and move_id.purchase_line_id.order_id.engage_id.id or False
                if engage_id and not (engage_id in engage_ids):
                    engage_ids.append(engage_id)
        wf_service = netsvc.LocalService('workflow')
        #On vérifie que toutes les réceptions de produits sont faites
        for engage_id in engage_ids:
            wf_service.trg_validate(uid, 'open.engagement', engage_id, 'signal_received', cr)
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
    
    def name_search(self, cr, uid, name='', args=[], operator='ilike', context=None, limit=80):
        ids = self.search(cr, uid, args, limit=limit, context=context)
        return self.name_get(cr, uid, ids,context=context)
    
    def search(self, cr, uid, args=[], offset=0, limit=None, order=None, context=None, count=False):
        if context and context is not None:
            if 'only_my_services' in context:
                my_args = [('id','in',[x.id for x in self.pool.get("res.users").browse(cr,uid,uid,context=context).service_ids])]
                return super(openstc_service, self).search(cr, uid, args + my_args, offset=offset, limit=limit, order=order, context=context, count=count)
        return super(openstc_service, self).search(cr, uid, args, offset=offset, limit=limit, order=order, context=context, count=count)
    
    _columns = {
        'accountant_service':fields.selection([('cost','cost center'),('production','production center')],'Service comptable'),
        'code_serv_ciril':fields.char('Ciril Service Code',size=8, help="this field refer to service pkey from Ciril instance"),
        'purchase_order_ids':fields.one2many('purchase.order','service_id','Purchases made by this service'),
        'purchase_order_ask_ids':fields.one2many('purchase.order.ask','service_id','Purchase Asks made by this service'),
        'open_engagement_ids':fields.one2many('open.engagement','service_id','Engages made by this service'),
        }
    
openstc_service()
    
