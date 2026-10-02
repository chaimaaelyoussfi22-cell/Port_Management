# -*- coding: utf-8 -*-
"""Package des pages Streamlit (dashboard, saisie, rapports).

Initialisé comme package régulier afin que `from pages.<module> import ...`
fonctionne de façon robuste sous le runtime Streamlit (multipage + namespace
package) et d'éviter un `KeyError: 'pages'` à l'import.
"""
