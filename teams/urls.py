from django.urls import path
from . import views

urlpatterns = [
    path('', views.roster_view, name='roster'),
    path('create/', views.team_create_view, name='team_create'),
    path('settings/', views.team_settings_view, name='team_settings'),
    path('player/add/', views.player_add_view, name='player_add'),
    path('player/<int:pk>/', views.player_profile_view, name='player_profile'),
    path('player/<int:pk>/edit/', views.player_edit_view, name='player_edit'),
    path('player/<int:pk>/delete/', views.player_delete_view, name='player_delete'),
    path('invite/', views.invite_view, name='invite'),
    path('invite/<uuid:token>/accept/', views.accept_invite_view, name='accept_invite'),
    path('announcements/create/', views.create_announcement_view, name='create_announcement'),
]
