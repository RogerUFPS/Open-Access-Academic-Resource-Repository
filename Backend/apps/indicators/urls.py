from django.urls import path

from .views import IndicatorsView


urlpatterns = [
    path("", IndicatorsView.as_view(), name="indicators"),
]
