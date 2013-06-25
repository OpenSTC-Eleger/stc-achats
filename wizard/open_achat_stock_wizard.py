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

class openstc_open_engage_refuse_inv_wizard(osv.osv_memory):
    _name = "openstc.open.engage.refuse.inv.wizard"
    _columns = {
        'justif_refuse':fields.text('Justificatif du Refus de paiement de la facture',required=True),
        }

    def to_refuse(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        wizard = self.browse(cr, uid, ids, context)
        assert 'attach_id' in context, "Context Value Error, attach_id must be in context when displaying wizard, check action_refuse_invoice_to_pay of ir_attachment"
        attach = self.pool.get("ir.attachment").browse(cr, uid, context['attach_id'], context)
        #On indique le msg que devra afficher le mail
        self.pool.get("purchase.order").write(cr, uid, attach.res_id, {'justificatif_refus':wizard.justif_refuse}, context=context)
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



class openstc_report_service_site_cost(osv.osv):
    _name = "openstc.report.service.site.cost.wizard"
    _columns = {
        }
    
    def print_report(self, cr, uid, ids, context=None):
        return {'type':'ir.actions.report.xml','report_name':'jasper.brunoreport'}

openstc_report_service_site_cost()
    
class openstc_pret_emprunt_wizard(osv.osv):
    _inherit = "openstc.pret.emprunt.wizard"
    
    def prepare_sale_order(self, cr, uid, default_location_id, partner_id, purchase_lines, origin=False):
        res = super(openstc_pret_emprunt_wizard, self).prepare_sale_order(cr, uid, default_location_id, partner_id, purchase_lines, origin)
        res.update({'validation':'done'})
        return res
    
openstc_pret_emprunt_wizard()

class open_engagement_check_elu_wizard(osv.osv_memory):
    _name = "open.engagement.check.elu.wizard"
    _columns = {
        'justif_check':fields.text('Justification de l\'Autorisation', required=True),
        }
    
    def check_elu(self, cr, uid ,ids, context=None):
        if 'po_id' in context:
            if isinstance(ids, list):
                ids = ids[0]
            wizard = self.browse(cr, uid, ids, context)
            self.pool.get("purchase.order").write(cr, uid, context['po_id'], {'justif_check':wizard.justif_check})
            return self.pool.get("purchase.order").check_elu(cr, uid, [context['po_id']], context)

        return False
open_engagement_check_elu_wizard()