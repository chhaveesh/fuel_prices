from django.urls import path

from .views import TripPlanView, trip_map

urlpatterns = [
    path("route/", TripPlanView.as_view(), name="trip-plan"),
    path("route/map/", trip_map, name="trip-map"),
]
