from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def index(request):
    return JsonResponse({
        "service": "Fuel Route Optimizer API",
        "endpoints": {
            "plan_trip_json": "/api/route/?start=Chicago, IL&finish=Denver, CO",
            "plan_trip_map": "/api/route/map/?start=Chicago, IL&finish=Denver, CO",
        },
        "params": {
            "start / finish": "'City, ST' or 'lat,lng' (USA only)",
            "include_route": "true|false (default true): include route GeoJSON",
        },
    })


urlpatterns = [
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
]
