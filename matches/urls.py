from django.urls import path
from . import views

urlpatterns = [
    path('<int:match_id>/start/', views.start_match, name='start_match'),
    path('<int:match_id>/live/', views.live_match_view, name='live_match'),
    path('<int:match_id>/state/', views.match_state, name='match_state'),
    path('<int:match_id>/point/', views.record_point, name='record_point'),
    path('<int:match_id>/rotate/', views.manual_rotate, name='manual_rotate'),
    path('<int:match_id>/sub/', views.make_substitution, name='make_substitution'),
    path('<int:match_id>/libero/', views.libero_swap, name='libero_swap'),
    path('<int:match_id>/timeout/', views.call_timeout, name='call_timeout'),
    path('<int:match_id>/lineup/', views.set_lineup, name='set_lineup'),
    path('<int:match_id>/contrast/', views.toggle_high_contrast, name='toggle_high_contrast'),
]
