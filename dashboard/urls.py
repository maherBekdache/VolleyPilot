from django.urls import path
from . import views

urlpatterns = [
    path('statistics/', views.statistics_view, name='statistics'),
    path('results/', views.results_view, name='results'),
    path('export/csv/', views.export_stats_csv, name='export_stats_csv'),
    path('export/pdf/', views.export_stats_pdf, name='export_stats_pdf'),
]
