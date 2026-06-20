"""Widgets Élu — module init."""

from dashboard.components.widgets.elu.bottleneck_map import render_bottleneck_map
from dashboard.components.widgets.elu.bottleneck_ranking import render_bottleneck_ranking
from dashboard.components.widgets.elu.cost_estimate import render_cost_estimate
from dashboard.components.widgets.elu.data_quality_badge import render_data_quality_badge
from dashboard.components.widgets.elu.delta_kpis import render_delta_kpis
from dashboard.components.widgets.elu.drift_status_badge import render_drift_status_badge
from dashboard.components.widgets.elu.executive_summary import render_executive_summary
from dashboard.components.widgets.elu.impact_projection import render_impact_projection
from dashboard.components.widgets.elu.kpi_cards import render_kpi_cards
from dashboard.components.widgets.elu.map_painter import render_map_painter
from dashboard.components.widgets.elu.network_health_gauge import (
    render_network_health_gauge,
)
from dashboard.components.widgets.elu.news_section import render_news_section
from dashboard.components.widgets.elu.pdf_generator import render_pdf_generator
from dashboard.components.widgets.elu.project_selector import render_project_selector
from dashboard.components.widgets.elu.roi_calculator import render_roi_calculator
from dashboard.components.widgets.elu.slide_builder import render_slide_builder
from dashboard.components.widgets.elu.template_selector import render_template_selector
from dashboard.components.widgets.elu.top_decisions import render_top_decisions
from dashboard.components.widgets.elu.trend_chart import render_trend_chart

__all__ = [
    "render_bottleneck_map",
    "render_bottleneck_ranking",
    "render_cost_estimate",
    "render_data_quality_badge",
    "render_delta_kpis",
    "render_drift_status_badge",
    "render_executive_summary",
    "render_impact_projection",
    "render_kpi_cards",
    "render_map_painter",
    "render_network_health_gauge",
    "render_news_section",
    "render_pdf_generator",
    "render_project_selector",
    "render_roi_calculator",
    "render_slide_builder",
    "render_template_selector",
    "render_top_decisions",
    "render_trend_chart",
]
