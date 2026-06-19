"""Widgets Pro TCL — module init."""

# Sprint 15+ (audit Pro TCL B-22) : Pro_5_Export (page stub) +
# saeiv_export + export_button ont été supprimés. La page exportait du
# JSON placeholder (WeasyPrint stub non branché). Décision utilisateur
# 2026-06-19 : virer du sidebar. Les exports SAEIV/Hastus sont reportés
# à un Sprint ultérieur quand les connecteurs seront réels.

from dashboard.components.widgets.pro_tcl.alert_ticker import render_alert_ticker
from dashboard.components.widgets.pro_tcl.before_after_chart import render_before_after_chart
from dashboard.components.widgets.pro_tcl.cause_analysis import render_cause_analysis
from dashboard.components.widgets.pro_tcl.coherence_scatter import render_coherence_scatter
from dashboard.components.widgets.pro_tcl.correlation_matrix import render_correlation_matrix
from dashboard.components.widgets.pro_tcl.format_selector import render_format_selector
from dashboard.components.widgets.pro_tcl.frequency_slider import render_frequency_slider
from dashboard.components.widgets.pro_tcl.gnn_map import (
    render_gnn_map_section,
    render_traffic_map,
    render_traffic_map_compact,
)
from dashboard.components.widgets.pro_tcl.line_comparison import render_line_comparison
from dashboard.components.widgets.pro_tcl.line_kpis import render_line_kpis
from dashboard.components.widgets.pro_tcl.line_selector import render_line_selector
from dashboard.components.widgets.pro_tcl.model_monitoring import render_model_monitoring_page
from dashboard.components.widgets.pro_tcl.network_map import render_network_map
from dashboard.components.widgets.pro_tcl.otp_filters import render_otp_filters
from dashboard.components.widgets.pro_tcl.otp_heatmap import (
    render_otp_heatmap,
    render_otp_heatmap_mini,
)
from dashboard.components.widgets.pro_tcl.otp_projection import render_otp_projection
from dashboard.components.widgets.pro_tcl.pipeline_management import render_pipeline_management_page
from dashboard.components.widgets.pro_tcl.report_builder import render_report_builder
from dashboard.components.widgets.pro_tcl.segment_table import render_segment_table

__all__ = [
    "render_alert_ticker",
    "render_before_after_chart",
    "render_cause_analysis",
    "render_coherence_scatter",
    "render_correlation_matrix",
    "render_format_selector",
    "render_frequency_slider",
    "render_gnn_map_section",
    "render_line_comparison",
    "render_line_kpis",
    "render_line_selector",
    "render_model_monitoring_page",
    "render_network_map",
    "render_otp_filters",
    "render_otp_heatmap",
    "render_otp_heatmap_mini",
    "render_otp_projection",
    "render_pipeline_management_page",
    "render_report_builder",
    "render_segment_table",
    "render_traffic_map",
    "render_traffic_map_compact",
]
