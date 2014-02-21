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




import time
from report import report_sxw
from datetime import datetime

class po_ask(report_sxw.rml_parse):
    def __init__(self, cr, uid, name, context):
        super(po_ask, self).__init__(cr, uid, name, context)
        self.localcontext.update({
            'time': time,
            'datetime':datetime,
        })

report_sxw.report_sxw('report.purchase.order.ask', 'purchase.order.ask',
      'addons/openstc_achat_stock/report/request_quotation.rml', parser=po_ask)

class po_sumup(report_sxw.rml_parse):
    def __init__(self, cr, uid, name, context):
        super(po_sumup, self).__init__(cr, uid, name, context)
        self.localcontext.update({
            'time': time,
            'datetime':datetime,
        })

report_sxw.report_sxw('report.purchase.order.sumup', 'purchase.order',
      'addons/openstc_achat_stock/report/openstc_purchase_order_sumup.rml', parser=po_sumup)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: