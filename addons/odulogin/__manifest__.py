{
    "name": "OduLogin",
    "summary": "Let administrators inspect Odoo as another internal user",
    "description": """
OduLogin
========

Administrators can temporarily switch the current browser session to another
active internal user and return to their original account from the systray.
""",
    "version": "17.0.1.0.0",
    "category": "Administration",
    "author": "Oduflow",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/odulogin_switch_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "odulogin/static/src/js/switch_user_menu.js",
            "odulogin/static/src/xml/switch_user_menu.xml",
        ],
    },
    "application": False,
    "installable": True,
}
