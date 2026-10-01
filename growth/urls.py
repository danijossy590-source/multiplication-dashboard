from django.urls import path
from . import views

urlpatterns = [
    path('assignment/create/', views.assignment_create_view, name='assignment_create'),
    path('assignment/<int:assignment_id>/submit/', views.reflection_submit_view, name='reflection_submit'),
    path('reflection/<int:reflection_id>/', views.reflection_detail_view, name='reflection_detail'),
    path('dashboard/', views.multiplication_dashboard_view, name='multiplication_dashboard'),
    path('api/discipleship-tree/', views.discipleship_tree_api, name='discipleship_tree_api'),
]
