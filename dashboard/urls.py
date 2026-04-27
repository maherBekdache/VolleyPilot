from django.urls import path
from . import views

urlpatterns = [
    path('statistics/', views.statistics_view, name='statistics'),
    path('results/', views.results_view, name='results'),
    path('ai-analytics/', views.ai_analytics_view, name='ai_analytics'),
    path('ai-analytics/export-anonymized/', views.export_anonymized_dataset, name='export_anonymized_dataset'),
    path('ai-analytics/volypilot/', views.volypilot_chat, name='volypilot_chat'),
    path('export/csv/', views.export_stats_csv, name='export_stats_csv'),
    path('export/pdf/', views.export_stats_pdf, name='export_stats_pdf'),
]
