{
    "name": "Odubook",
    "summary": "Interactive documentation assembled from installed modules",
    "description": """
Book
====

The documentation module responsible for built-in documentation. It scans
installed modules, collects Markdown files from their ``doc`` folders and
dynamically assembles them into an interactive book inside the Odoo UI.

No separate wiki -- the documentation lives next to the module code and is
shown to the user in a single click.
""",
    "version": "19.0.1.0.0",
    "category": "Tools",
    "author": "VelesAgro, Oduflow",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "security/odubook_security.xml",
        "views/odubook_views.xml",
        "views/odubook_users_views.xml",
    ],
    "demo": ["data/odubook_manual_data.xml"],
    "assets": {
        "web.assets_backend": [
            "odubook/static/src/book/book.scss",
            "odubook/static/src/book/book.js",
            "odubook/static/src/admin/adminbook.js",
            "odubook/static/src/changes/changes.js",
            "odubook/static/src/manuals/manuals.js",
            "odubook/static/src/user_menu/language.js",
            "odubook/static/src/book/book.xml",
            "odubook/static/src/changes/changes.xml",
            "odubook/static/src/manuals/manuals.xml",
            "odubook/static/src/user_menu/language.xml",
        ],
    },
    "application": True,
    "installable": True,
}
