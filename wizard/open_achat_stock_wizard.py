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
    _columns = {
            'analytic_account_id':fields.many2one('account.analytic.account','Compte associé à l\'achat'),
            'po_ammount':fields.float('Montant de l\'achat', digit=(5,2)),
            'budget_dispo':fields.float('Budget Disponible', digit(6,2), readonly=True),
            'tx_erosion': fields.float('Taux Erosion de votre Service', digit=(2,2), readonly=True),
     }
    
    def default_get(self, cr, uid, ids, name, args, context=None):
        ret = super(purchase_order_ask_verif_budget, self).defalut_get(cr, uid, ids, name ,args, context)
        if ('ammount_total','po_id') in context:
            ret.update({'po_ammount':context['ammount_total']})
        return ret
    
    def onchange_analytic_account_id(self, cr, uid, ids, analytic_account_id=False, context=None):
        if analytic_account_id:
            line_id = self.pool.get("crossovered.budget.line").search(cr, uid, [('analytic_account_id','=',analytic_account_id)])
            if not line_id:
                return {'warning':{'Erreur','Ce compte Analytique n appartient a aucune ligne budgetaire'}}
            if isinstance(line_id):
                line_id = line_id[0]
                print("Warning, un meme compte analytique est present dans plusieurs lignes de budgets")
            line = self.pool.get("crossovered.budget.line").browse(cr, uid, line_id)
            res = line.planned_amount - line.practical_ammount
            return {'value':{'budget_dispo':res}}
        return {'value':{}}
    
purchase_order_ask_verif_budget()
    

