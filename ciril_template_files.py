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

import logging
import os
import re
import unicodedata
from datetime import datetime
_logger = logging.getLogger('openerp')

"""@note: Remove all char that is an accent (category 'Mn' according to unicode RFC 5.2 used by python) """
def to_upper_unaccent(str):
    return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x) <> 'Mn').upper()

class item_file(object):
    value = ''
    length = 0
    pos = 0
    mandatory = False
    
    def __init__(self, value='', length=10, pos=0, mandatory=True):
        self.value = value
        self.length = length
        self.pos = pos
        self.mandatory = mandatory
    
    def serialize(self):
        return {'value':self.value,'length':self.length,'pos':self.pos,'mandatory':self.mandatory}
    
    def __getitem__(self, key):
        return self.__getattribute__(key)
    
    def __setitem__(self, key, value):
        return self.__setattr__(key, value)
        

class template_ciril_txt_file_engagement(object):
    
    _vars = {}
    _version = ''
    
    def format_float(self, value):
        ret = ''
        temp_val = value * 100.0
        ret += str(int(temp_val))
#        decimal = temp_val - int(temp_val)
#        if decimal:
#            ret += str(decimal)[2:]
        return int(ret)
    
    def format_datas(self, datas):
        ret = ''
        for data in datas:
            if len(ret) > 0:
                ret += '\n'
            for (key, it) in data:
                missing = it['length'] - len(unicode(it['value']))
                if missing <= 0:
                    #we just supply the string to the maximum length authorized for this field
                    ret += unicode(it['value'])[:it['length']]
                else:
                    #otherwise, we complete non registered characters with default ones, spaces suffixing strings field and 0 prefixing numeric fields
                    if isinstance(it['value'], (int,long, float)):
                        ret += ''.join(['0' for i in range(missing)]) + unicode(it['value'])
                    else:
                        ret += it['value'] + ''.join([' 'for i in range(missing)])
        return ret
    
    def format_code_nature(self, code):
        res = re.search("[1-9][0-9]*[1-9]",code)
        if res is not None:
            return res.group(0)
        return code
    
    def __init__(self, version='B'):
        self._version = version
        _logger.info('Initialized template file for engages at version %s' % self._version)

    def init_main_vals(self):
        return {'code_tiers':{'length':10,'required':True,'value':'','pos':1},
                    'num_ope':{'length':10,'required':True,'value':'','pos':5},
                    'exercice':{'length':4,'required':True,'value':'','pos':10},
                    'date_engage':{'length':10,'required':True,'value':'','pos':11},
                    'code_user':{'length':10,'required':True,'value':'CIRIL','pos':12},
                    'type_engage':{'length':2,'required':True,'value':'','pos':14},
                    'origin':{'length':2,'required':True,'value':'S','pos':15},
                    'num_market':{'length':10,'required':False,'value':'','pos':20},
                    'num_lot':{'length':10,'required':False,'value':'','pos':21},
                    'num_commande_openstc':{'length':64,'required':False,'value':'','pos':28},
                    'code_origin_numerotation':{'length':2,'required':False,'value':'OE','pos':29},
                    }
    
    def init_line_vals(self):
        return {
                    'code_gest':{'length':10,'required':True,'value':'','pos':2},
                    'code_ss_rub':{'length':7,'required':True,'value':'','pos':3},
                    'code_nature':{'length':10,'required':True,'value':'','pos':4},
                    'code_serv':{'length':4,'required':True,'value':'','pos':6},
                    'code_antenne':{'length':10,'required':True,'value':'','pos':7},
                    'depense_recette':{'length':1,'required':True,'value':'','pos':8},
                    'code_budget':{'length':2,'required':True,'value':'','pos':9},
                    'code_tva':{'length':2,'required':False,'value':0,'pos':13},
                    'amount_ht':{'length':16,'required':True,'value':0,'pos':16},
                    'amount_tva':{'length':16,'required':True,'value':0,'pos':17},
                    'num_engage':{'length':10,'required':False,'value':'','pos':19},
                    'string':{'length':120,'required':True,'value':'','pos':18},
                    'nomenclature':{'length':10,'required':False,'value':'','pos':22},
                    'motif_rejet':{'length':50,'required':False,'value':'','pos':23},
                    'type_depense':{'length':2,'required':False,'value':'','pos':24},
                    'objectif':{'length':11,'required':False,'value':'','pos':25},
                    'version':{'length':1,'required':True,'value':self._version,'pos':26},
                    'num_engage_openstc':{'length':64,'required':False,'value':'','pos':27},
                    }
    
    def create_file(self, record, code_gest='TECHN'):
        if not self._vars:
            _logger.warning('Trying to use template for engagement without initializing it, forcing init method to it\'s latest version')
            self.__init__()
        #assert not isinstance(record, osv.osv), 'Error, you passed a none osv object to the template file'
        assert record._name == 'purchase.order', 'Error, you try to write an engage without an purchase.order object'
        
        #data_main = self._vars.copy()
        data_main = self.init_main_vals()
        datas = []
        ret = ''
        #associate corresponding data for each file field
        
        #data['code_ss_rub']['value']
        #data['num_lot']['value'] = record.purchase_order_id.partner_id.id
        #data['num_ope']['value']
        #data['code_user']['value']
        #data['origin']['value']
        #data_main['num_market']['value'] = record.purchase_order_id.partner_id.id
        #data_main['num_commande']['value'] = record.purchase_order_id.partner_id.id
        
        data_main['code_tiers']['value'] = str(record.partner_id.code_tiers_ciril or '') 
        data_main['num_commande_openstc']['value'] = record.name
        data_main['exercice']['value'] = record.date_engage_validated[:4]
        data_main['date_engage']['value'] = record.date_engage_validated[:10]
        data_main['type_engage']['value'] = 'I'
        
        for line in record.engage_lines:
            data = self.init_line_vals()
            data['code_gest']['value'] = line.budget_line_id.crossovered_budget_id.service_id.code_gest_ciril
            data['code_ss_rub']['value'] = line.budget_line_id.crossovered_budget_id.service_id.code_function_ciril
            data['num_engage_openstc']['value'] = line.name
            data['code_serv']['value'] = line.budget_line_id.crossovered_budget_id.service_id.code_serv_ciril
            now = datetime.now()
            budget_line = line.budget_line_id
            if budget_line.date_from <= str(now) and budget_line.date_to >= str(now):        
                data['code_nature']['value'] = budget_line.openstc_general_account and self.format_code_nature(budget_line.openstc_general_account.code) or ''
                data['code_antenne']['value'] = budget_line.openstc_code_antenne or ''
                data['code_budget']['value'] = budget_line.crossovered_budget_id.code_budget_ciril or ''
            #data['nomenclature']['value'] = record.purchase_order_id.partner_id.id
            #data['motif_rejet']['value'] = record.purchase_order_id.partner_id.id
            #data['version']['value']
            #data['type_depense']['value'] = 
            #data['objectif']['value'] = 
            
            #TOREPLACE with real ids of service and site
#            if len(line.order_line) == 1:
#                if len(line.order_line[0].merge_line_ids) == 1:
#                    data['code_antenne']['value'] = str(line.order_line[0].merge_line_ids[0].site_id.id)
#                    data['code_serv']['value'] = str(line.order_line[0].merge_line_ids[0].service_id.id)
            data['code_tva']['value'] = line.order_line[0].taxes_id and line.order_line[0].taxes_id[0].code_tax_ciril or '' 
            data['depense_recette']['value'] = 'D'
            #TOREPLACE with real ids
            data['string']['value'] = to_upper_unaccent(record.description)
            #TODO: keep a trace of current code numerotation
            #num_engage and code_origin are exclusive each other
            #data['num_engage']['value'] = line.name
            
            amount_ht = 0
            for order_line in line.order_line:
                amount_ht += order_line.price_subtotal
            data['amount_ht']['value'] = self.format_float(amount_ht)
            data['amount_tva']['value'] = self.format_float(line.amount - amount_ht)
            #sort data dictionnary
            data2 = sorted(data.items() + data_main.items(), key=lambda item: item[1]['pos'])
            datas.append(data2)
        
        ret = self.format_datas(datas)
        return ret

    