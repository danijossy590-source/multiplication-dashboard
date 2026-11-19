from django.urls import path
from . import views

urlpatterns = [
    path('', views.pod_list_view, name='pod_list'),
    path('join/', views.pod_join_view, name='pod_join'),
    path('create/', views.pod_create_view, name='pod_create'),
    path('<int:pod_id>/delete/', views.pod_delete_view, name='pod_delete'),
    path('<int:pod_id>/', views.pod_detail_view, name='pod_detail'),
    path('launch-apprentice/', views.launch_apprentice_pod_view, name='launch_apprentice'),
]


