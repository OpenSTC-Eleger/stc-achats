# -*- coding: utf-8 -*-

##############################################################################
#    Copyright (C) 2012 SICLIC http://siclic.fr
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
#############################################################################

from osv import osv, fields
from tools.translate import _
from openbase.openbase_core import OpenbaseCore

#class account_analytic_account(OpenbaseCore):
#    _inherit = "account.analytic.account"
#    _name = "account.analytic.account"
#    
#    _columns = {
#        'code_antenne':fields.char('Antenne Code', size=16, help='Antenne code from CIRIL instance'),
#        }
#    
#account_analytic_account()

class account_invoice_line(OpenbaseCore):
    _inherit = "account.invoice.line"
    _name = "account.invoice.line"
    
    _columns = {
        'merge_line_ids':fields.one2many('openstc.merge.line.ask', 'invoice_line_id','Regroupement des Besoins')
        }
    
    def _check_qte_merge_qte_invoice(self, cr, uid, ids, context=None):
        for line in self.browse(cr, uid, ids, context):
            qte_ref = line.quantity
            qte = 0
            for merge_line in line.merge_line_ids:
                if not merge_line.product_id or merge_line.product_id.id == line.product_id.id:
                    qte += merge_line.qty_remaining
                else:
                    raise osv.except_osv(_('Error'),_('you have associcated merge lines that does not rely to order line product'))
            if qte_ref < qte:
                return False
            else:
                return True
        return False
    
    _constraints = [(_check_qte_merge_qte_invoice,_('Error, product qty is lower than product qty of summed merge lines you have associated to this order line'),['product_id','merge_line_ids'])]
        
account_invoice_line()
 

class account_invoice(OpenbaseCore):
    _inherit = "account.invoice"
    _name = "account.invoice"
    _columns = {
        }
    #Ecrit pour les merge_lines le move_line associé à la ligne de facture
    def action_number(self, cr, uid, ids, context=None):
        if super(account_invoice, self).action_number(cr, uid, ids, context):
            move_line_obj = self.pool.get("account.move.line")
            for inv in self.browse(cr, uid, ids, context):
                analytic_lines_by_prod = {}
                #On lie chaque produit au move_line auquel il est associé
                for move_line in inv.move_id.line_id:
                    #TOCHECK: ne prendre que les move_line de débits ? (Correspondant à l'achat?)
                    if move_line.debit > 0.0:
                        analytic_lines_by_prod.update({move_line.product_id.id:move_line.id})
                #Puis pour chaque ligne de facture de l'objet en cours, on lie le move_id aux merge_lines associés
                for line in inv.invoice_line:
                    if line.product_id.id in analytic_lines_by_prod:
                        #Si un besoin est recensé par la facture, on le lie avec le move_line, sinon c'est une écriture classique de move_line
                        if line.merge_line_ids:
                            move_line_obj.write(cr, uid, analytic_lines_by_prod[line.product_id.id], {'merge_line_ids':[(4,x.id) for x in line.merge_line_ids]}, context)
            return True
        return False

account_invoice()

class account_move_line(OpenbaseCore):
    _inherit = "account.move.line"
    _name = "account.move.line"
    _columns = {
        'merge_line_ids':fields.one2many('openstc.merge.line.ask','move_line_id','Besoins en Fournitures associés'),
        }
    
    def _check_prod(self, cr, uid, ids, context=None):
        for move_line in self.browse(cr, uid, ids, context):
            for merge_line in move_line.merge_line_ids:
                if not merge_line.product_id or merge_line.product_id.id <> move_line.product_id.id:
                    return False
            return True
        return True
    _constraints = [(_check_prod,_('Error, All merge lines associated to this move line does not match same product as this move line'),['product_id','merge_line_ids'])]

    
account_move_line()
    
class account_tax(OpenbaseCore):
    _inherit = "account.tax"
    _name = "account.tax"
    _columns = {
        'code_tax_ciril':fields.char('Ciril Tax Code', size=8, help="this field refer to Tax Code from Ciril instance"),
        }
        
account_tax()

class account_analytic_account(OpenbaseCore):
    _inherit = "account.analytic.account"
account_analytic_account()

class account_account(OpenbaseCore):
    _inherit = "account.account"
    
    def _get_complete_name(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, '')
        for account in self.browse(cr, uid, ids, context=context):
            ret[account.id] = account.name_get()[0][1] 
        return ret
    
    _columns = {
        'complete_name': fields.function(_get_complete_name, method=True, type='char', store=True)
        }
    
    #add analytic purchase journal to purchase journal (m20 field)
    def init_stc_achat_accounting(self, cr, uid, analytic_journal_id, context=None):
        if analytic_journal_id:
            journal_id = self.pool.get("account.journal").search(cr, uid, [('type','=','purchase')])
            if journal_id:
                self.pool.get("account.journal").write(cr, uid, journal_id, {'analytic_journal_id':analytic_journal_id})
                return True
            print "Error, purchase journal not found"
            return False
        print "Error, analytic purchase journal not found"
        return False
    