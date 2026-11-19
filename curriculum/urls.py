from django.urls import path
from . import views

urlpatterns = [
    path('', views.lesson_list_view, name='lesson_list'),
    path('courses/create/', views.course_create_view, name='course_create'),
    path('courses/generate/', views.course_generate_view, name='course_generate'),
    path('courses/<int:course_id>/', views.course_detail_view, name='course_detail'),
    path('courses/<int:course_id>/modules/create/', views.module_create_view, name='module_create'),
    path('courses/<int:course_id>/certificate/', views.certificate_view, name='certificate'),
    path('modules/<int:module_id>/quiz/', views.quiz_view, name='quiz'),
    path('modules/<int:module_id>/quiz/manage/', views.quiz_manage_view, name='quiz_manage'),
    path('quiz/attempts/<int:attempt_id>/', views.quiz_result_view, name='quiz_result'),
    path('lessons/<int:lesson_id>/complete/', views.lesson_complete_view, name='lesson_complete'),
    path('lessons/<int:lesson_id>/edit/', views.lesson_edit_view, name='lesson_edit'),
    path('lessons/<int:lesson_id>/delete/', views.lesson_delete_view, name='lesson_delete'),
    path('create/', views.lesson_create_view, name='lesson_create'),
    path('lesson-assist/', views.lesson_assist_view, name='lesson_assist'),
    path('<int:lesson_id>/', views.lesson_detail_view, name='lesson_detail'),
    path('<int:lesson_id>/teach-this/', views.teach_this_view, name='teach_this'),
]
