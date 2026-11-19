from django.urls import path
from . import views

urlpatterns = [
    path('', views.question_list_view, name='question_list'),
    path('ask/', views.question_create_view, name='question_create'),
    path('<int:question_id>/', views.question_detail_view, name='question_detail'),
    path('<int:question_id>/reply/', views.reply_create_view, name='reply_create'),
    path('<int:question_id>/report/', views.question_report_view, name='question_report'),
    path('replies/<int:reply_id>/report/', views.reply_report_view, name='reply_report'),
]
