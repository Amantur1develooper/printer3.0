from django.urls import path
from . import views

urlpatterns = [
    # Printer agent API
    path('jobs/', views.jobs_list, name='printer_jobs'),
    path('jobs/<int:order_id>/pickup/', views.job_pickup, name='printer_pickup'),
    path('jobs/<int:order_id>/complete/', views.job_complete, name='printer_complete'),
    path('jobs/<int:order_id>/error/', views.job_error, name='printer_error'),
]

dashboard_urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('printer/<int:terminal_id>/config.json', views.download_config, name='dashboard_config'),
    path('printer/<int:terminal_id>/agent.py', views.download_agent, name='dashboard_agent'),
]
