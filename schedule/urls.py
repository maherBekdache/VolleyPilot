from django.urls import path
from . import views

urlpatterns = [
    path('', views.schedule_view, name='schedule'),
    path('match/add/', views.match_create_view, name='match_create'),
    path('match/<int:pk>/edit/', views.match_edit_view, name='match_edit'),
    path('match/<int:pk>/cancel/', views.match_cancel_view, name='match_cancel'),
    path('practice/add/', views.practice_create_view, name='practice_create'),
    path('practice/<int:pk>/edit/', views.practice_edit_view, name='practice_edit'),
    path('practice/<int:pk>/', views.practice_detail_view, name='practice_detail'),
    path('availability/<str:event_type>/<int:pk>/request/', views.request_availability_view, name='request_availability'),
    path('availability/respond/<int:pk>/', views.availability_respond_view, name='availability_respond'),
    path('availability/<str:event_type>/<int:pk>/summary/', views.availability_summary_view, name='availability_summary'),
]
