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

{
    "name": "openstc_achat_stock",
    "version": "0.1",
    "depends": ["purchase", "account_accountant", "product", "stock", "analytic", "account_budget", "openbase"],
    "author": "PYF & BP",
    "category": "Category",
    "description": """
    Module OpenSTC ACHAT - STOCKS pour collecticités territoriales.
    Gestion des fournitures par service de Collectivité (ST, écoles, etc...) ainsi que du process de réapprovisionnement.
    Fonctionnalités principales : 
        - Génération de bons de commandes
        - Gestion du Budget par service
        - Demandes de Fournitures
    
    Ce module nécessite l'installation de openstc.
    """,
    "data": [
        "views/open_achat_stock_data.xml",
        "views/sequence.xml",
        
        "views/openstc_achat_stock_board_view.xml",
        "views/openstc_achat_stock_budget_views.xml",
        "views/open_achat_stock_menu_view.xml",
        "views/open_achat_stock_wizard_view.xml",
        "views/open_achat_stock_view.xml",
        "views/openstc_achat_stock_report.xml",
        
        "workflow/openstc_achat_stock_workflow.xml",
        
        "security/openstc_achat_stock_security.xml",
        "security/ir.model.access.csv",
        
        #"unit_tests/unit_tests.xml",
        #"test/cr_commit.yml", "test/openachats_tests_data.xml","test/openstc_achats_devis_tests.yml", "test/openstc_achats_commande_tests.yml", "test/openstc_achats_suivi_commandes_tests.yml",
             ],
    "init_xml":["views/openstc_achat_stock_init_data.xml"],
    "demo": [],
    "test": [],
    "installable": True,
    "active": False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
