# HydroChat Django URLs Configuration
# Phase 11: API endpoint routing for HydroChat conversation service

from django.urls import path
from . import views

app_name = 'hydrochat'

urlpatterns = [
    # Main conversation endpoint
    path('converse/', views.ConverseAPIView.as_view(), name='converse'),
    
    # Statistics endpoint
    path('converse/stats/', views.ConverseStatsAPIView.as_view(), name='converse_stats'),
    
    # Phase 17: Metrics export endpoint (developer-only)
    path('metrics/export/', views.MetricsExportAPIView.as_view(), name='metrics_export'),
]
