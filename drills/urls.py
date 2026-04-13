from django.urls import path
from . import views

urlpatterns = [
    path('', views.drill_list_view, name='drill_list'),
    path('create/', views.drill_create_view, name='drill_create'),
    path('<int:pk>/edit/', views.drill_edit_view, name='drill_edit'),
    path('assign/<int:practice_id>/', views.assign_drill_view, name='assign_drill'),
    path('remove/<int:pk>/', views.remove_drill_from_practice_view, name='remove_drill_from_practice'),
    path('observations/<int:practice_id>/', views.drill_observation_view, name='drill_observations'),
]
