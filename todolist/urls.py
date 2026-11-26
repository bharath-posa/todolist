from django.urls import path
from . import views, views_extra, views_push

app_name = 'todolist'
urlpatterns=[
    path('', views.index, name='index'),
    path('additem/', views.additem , name='additem'),
    path('quickadd/', views.quick_add, name='quick_add'),
    path('login/', views.login, name='login'),
    path('adduser/', views.addUser, name='addUser'),
    path('signout/', views.signout, name='signout'),
    path('thanks/', views.thanks, name='thanks'),
    path('ajax/update_item_status', views.update_item_status, name='update_item_status'),
    path('editItem/<int:id>', views.edit_item, name="edit_item"),
    path('deleteItem/<int:id>', views.deleteItem, name="deleteItem"),
    path('pomodorotimer/<int:id>', views.pomodoroTimer, name="pomodoroTimer"),
    path('pomodorotimer/ajax/updatepomodoro', views.updatePomodoroCount, name="updatePomodoroCount"),
    path('projects/', views_extra.projects, name='projects'),
    path('projects/new/', views_extra.project_edit, name='project_new'),
    path('projects/<int:id>/', views_extra.project_detail, name='project'),
    path('projects/<int:id>/edit/', views_extra.project_edit, name='project_edit'),
    path('projects/<int:id>/delete/', views_extra.project_delete, name='project_delete'),
    path('metrics/', views_extra.metrics, name='metrics'),
    path('metrics/<int:id>/', views_extra.metric, name='metric'),
    path('metrics/<int:id>/delete/', views_extra.metric_delete, name='metric_delete'),
    path('metrics/entries/<int:id>/delete/', views_extra.entry_delete, name='entry_delete'),
    path('insights/', views_extra.insights, name='insights'),
    path('sw.js', views_push.service_worker, name='service_worker'),
    path('manifest.webmanifest', views_push.manifest, name='manifest'),
    path('notifications/', views_push.notifications, name='notifications'),
    path('notifications/subscribe/', views_push.subscribe, name='push_subscribe'),
    path('notifications/unsubscribe/', views_push.unsubscribe, name='push_unsubscribe'),
    path('notifications/test/', views_push.test, name='push_test'),
    path('notifications/devices/<int:id>/remove/', views_push.remove_device, name='push_remove_device'),
    
]