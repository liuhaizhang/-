from django.urls import path
from . import views

urlpatterns = [
    path('add', views.add, name='add_user'),
    path('update', views.update, name='update_user'),
    path('delete', views.delete, name='delete_user'),
    path('deleteByIds', views.delete_ids, name='delete_user_by_ids')
]
