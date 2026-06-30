"""Widgets partages entre personas (Usager, Pro TCL, Elu).

Les widgets ici sont utilises par plusieurs personas. Ils sont definis
dans leur module d'origine et re-exportes ici pour que les pages non-Pro
n'importent pas directement depuis widgets/pro_tcl/.
"""

from dashboard.components.widgets.pro_tcl.traffic_map import render_traffic_map_compact

__all__ = [
    "render_traffic_map_compact",
]
