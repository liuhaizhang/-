from django.urls import path
from . import views

urlpatterns = [
    path('getSlideLabelData', views.get_slide_label_data, name='getSlideLabelData'),

]