from django.urls import path
from . import views

urlpatterns = [
    path('', views.pod_list_view, name='pod_list'),
    path('join/', views.pod_join_view, name='pod_join'),
    path('create/', views.pod_create_view, name='pod_create'),
    path(
        '<int:pod_id>/books/<int:book_id>/read/',
        views.pod_book_read_view,
        name='pod_book_read',
    ),
    path(
        '<int:pod_id>/books/<int:book_id>/read/file/',
        views.pod_book_read_file_view,
        name='pod_book_read_file',
    ),
    path(
        '<int:pod_id>/books/<int:book_id>/sections/<int:section_id>/progress/',
        views.pod_book_section_progress_view,
        name='pod_book_section_progress',
    ),
    path('<int:pod_id>/books/<int:book_id>/file/', views.pod_book_file_view, name='pod_book_file'),
    path(
        '<int:pod_id>/books/<int:book_id>/reviews/<int:review_id>/comments/',
        views.pod_book_review_comment_view,
        name='pod_book_review_comment',
    ),
    path('<int:pod_id>/delete/', views.pod_delete_view, name='pod_delete'),
    path('<int:pod_id>/', views.pod_detail_view, name='pod_detail'),
    path('launch-apprentice/', views.launch_apprentice_pod_view, name='launch_apprentice'),
]


