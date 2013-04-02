# -*- coding: utf-8 -*-

import logging
import os

_logger = logging.getLogger('openerp')

class template_ciril_txt_file_engagement(object):
    
    _vars = {}
    
    def format_float(self, value):
        ret = ''
        ret += str(int(value))
        decimal = value - int(value)
        if decimal:
            ret += str(decimal)[2:]
        return int(ret)
    
    def format_datas(self, datas):
        ret = ''
        for item in datas:
            if len(ret) > 0:
                ret += '\n'
            for (key, it) in item:
                missing = it['length'] - len(str(it['value']))
                if missing <= 0:
                    #we just supply the string to the maximum length authorized for this field
                    ret += str(it['value'])[:it['length']]
                else:
                    #otherwise, we complete non registered characters with default ones, spaces suffixing strings field and 0 prefixing numeric fields
                    if isinstance(it['value'], (int,long, float)):
                        ret += ''.join(['0' for i in range(missing)]) + str(it['value'])
                    else:
                        ret += it['value'] + ''.join([' 'for i in range(missing)])
        return ret
    
    def __init__(self, version='B'):
        #lengths, mandatory and default values of each field 
        if version == 'B':
            self._vars = {'code_tiers':{'length':10,'required':True,'value':'','pos':1},
                    'code_gest':{'length':10,'required':True,'value':'','pos':2},
                    'code_ss_rub':{'length':7,'required':True,'value':'','pos':3},
                    'code_nature':{'length':10,'required':True,'value':'','pos':4},
                    'num_ope':{'length':10,'required':True,'value':'','pos':5},
                    'code_serv':{'length':4,'required':True,'value':'','pos':6},
                    'code_antenne':{'length':10,'required':True,'value':'','pos':7},
                    'depense_recette':{'length':1,'required':True,'value':'','pos':8},
                    'code_budget':{'length':2,'required':True,'value':'','pos':9},
                    'exercice':{'length':4,'required':True,'value':'','pos':10},
                    'date_engage':{'length':10,'required':True,'value':'','pos':11},
                    'code_user':{'length':10,'required':True,'value':'CIRIL','pos':12},
                    'code_tva':{'length':2,'required':False,'value':0,'pos':13},
                    'type_engage':{'length':2,'required':True,'value':'','pos':14},
                    'origin':{'length':2,'required':True,'value':'S','pos':15},
                    'amount_ht':{'length':16,'required':True,'value':0,'pos':16},
                    'amount_tva':{'length':16,'required':True,'value':0,'pos':17},
                    'string':{'length':120,'required':True,'value':'','pos':18},
                    'num_engage':{'length':10,'required':False,'value':'','pos':19},
                    'num_market':{'length':10,'required':False,'value':'','pos':20},
                    'num_lot':{'length':10,'required':False,'value':'','pos':21},
                    'nomenclature':{'length':10,'required':False,'value':'','pos':22},
                    'motif_rejet':{'length':50,'required':False,'value':'','pos':23},
                    'type_depense':{'length':2,'required':False,'value':'','pos':24},
                    'objectif':{'length':11,'required':False,'value':'','pos':25},
                    'version':{'length':1,'required':True,'value':'','pos':26},
                    'num_engage_openstc':{'length':64,'required':False,'value':'','pos':27},
                    'num_commande_openstc':{'length':64,'required':False,'value':'','pos':28},
                    'code_origin_numerotation':{'length':2,'required':False,'value':'','pos':29},
        }

    
    def create_file(self, record):
        if not self._vars:
            _logger.warning('Trying to use template for engagement without initializing it, forcing init method to it\'s latest version')
            self.__init__()
        #assert not isinstance(record, osv.osv), 'Error, you passed a none osv object to the template file'
        assert record._name == 'open.engagement', 'Error, you try to write an engage without an open.engagement object'
        
        data_main = self._vars.copy()
        datas = []
        ret = ''
        #associate corresponding data for each file field
        
        #data['code_gest']['value']
        #data['code_ss_rub']['value']
        #data['num_lot']['value'] = record.purchase_order_id.partner_id.id
        #data['num_ope']['value']
        #data['code_user']['value']
        #data['origin']['value']
        #data_main['num_market']['value'] = record.purchase_order_id.partner_id.id
        #data_main['num_commande']['value'] = record.purchase_order_id.partner_id.id
        
        #TOREPLACE: change it when we will have real tiers id from ciril instance
        data_main['code_tiers']['value'] = str(record.purchase_order_id.partner_id.id)
        #TOREPLACE with real ids
        data_main['code_nature']['value'] = '111111'
        data_main['num_engage_openstc']['value'] = record.name
        data_main['num_commande_openstc']['value'] = record.purchase_order_id.name
        data_main['exercice']['value'] = record.date_engage_validated[:4]
        data_main['date_engage']['value'] = record.date_engage_validated[:10]
        data_main['type_engage']['value'] = 'I'
        
        for line in record.engage_lines:
            data = data_main.copy()
            data['code_serv']['value'] = str(record.service_id.id)
            #data['code_antenne']['value']
            #data['nomenclature']['value'] = record.purchase_order_id.partner_id.id
            #data['motif_rejet']['value'] = record.purchase_order_id.partner_id.id
            #data['version']['value']
            #data['type_depense']['value'] = 
            #data['objectif']['value'] = 
            
            #TOREPLACE with real ids of service and site
            if len(line.order_line) == 1:
                if len(line.order_line[0].merge_line_ids) == 1:
                    data['code_antenne']['value'] = str(line.order_line[0].merge_line_ids[0].site_id.id)
                    data['code_serv']['value'] = str(line.order_line[0].merge_line_ids[0].service_id.id)
            data['code_tva']['value'] = line.order_line[0].taxes_id and line.order_line[0].taxes_id[0].id or '' 
            data['depense_recette']['value'] = 'D'
            #TOREPLACE with real ids
            data['code_budget']['value'] = str(line.account_analytic_id.id)
            data['string']['value'] = record.description
            data['num_engage']['value'] = line.name
            #TODO: keep a trace of current code numerotation
            data['code_origin_numerotation']['value'] = 'AA'
            
            amount_ht = 0
            for order_line in line.order_line:
                amount_ht += order_line.price_subtotal
            data['amount_ht']['value'] = self.format_float(amount_ht)
            data['amount_tva']['value'] = self.format_float(line.amount - amount_ht)
            #sort data dictionnary
            data2 = sorted(data.items(), key=lambda item: item[1]['pos'])
            datas.append(data2)
        
        ret = self.format_datas(datas)
        #TODO: finally, write content into a file in appending mode
        #TODO bis : or, write it in an ir.attachment
        return ret

    