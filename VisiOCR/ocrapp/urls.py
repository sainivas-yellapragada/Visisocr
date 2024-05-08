
from django.urls import path
from .views import home, upload_image, download_pdf

urlpatterns = [
    path('', home, name='home'),
    path('upload/', upload_image, name='upload_image'),
    path('download-pdf/', download_pdf, name='download_pdf'),
]
