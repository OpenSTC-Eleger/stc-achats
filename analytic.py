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

"""class account_analytic_default(osv.osv):
    _inherit = "account.analytic.default"
    
    _columns = {
        'site_id':fields.mane2one('openstc.site', 'Site'),
        }
    
account_analytic_default()"""
