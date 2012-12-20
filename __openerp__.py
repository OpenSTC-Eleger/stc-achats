# -*- coding: utf-8 -*-
##############################################################################
#
#   Openstc-oe
#
##############################################################################

{
    "name": "openstc_achat_stock",
    "version": "0.1",
    "depends": ["purchase", "product", "stock", "openstc", "account_budget"],
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
        "views/sequence.xml",
        
        "views/open_achat_stock_wizard_view.xml",
        "views/open_achat_stock_view.xml",
        "views/open_achat_stock_menu_view.xml",
             ],
    "demo": [],
    "test": [],
    "installable": True,
    "active": False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
