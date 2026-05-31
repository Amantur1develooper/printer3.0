from django.urls import path
from . import views

urlpatterns = [
    path('', views.map_view, name='map'),
    path('printer/<int:terminal_id>/upload/', views.upload_view, name='upload'),
    path('configure/<int:order_id>/', views.configure_view, name='configure'),
    path('ajax/calculate/', views.calculate_ajax, name='calculate_ajax'),
    path('payment/<int:order_id>/', views.payment_view, name='payment'),
    path('track/<str:order_number>/', views.tracking_view, name='tracking'),
    path('track/<str:order_number>/status/', views.tracking_status_ajax, name='tracking_status_ajax'),
]
