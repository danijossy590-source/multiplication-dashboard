from django.urls import path
from . import views

urlpatterns = [
    path('', views.lesson_list_view, name='lesson_list'),
    path('create/', views.lesson_create_view, name='lesson_create'),
    path('<int:lesson_id>/', views.lesson_detail_view, name='lesson_detail'),
    path('<int:lesson_id>/teach-this/', views.teach_this_view, name='teach_this'),
]

