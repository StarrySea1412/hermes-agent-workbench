from django.urls import path
from apps.files import views

urlpatterns = [
    path('files', views.list_files),
    path('files/upload', views.upload_file),
    path('files/<int:file_id>', views.delete_file),
]
