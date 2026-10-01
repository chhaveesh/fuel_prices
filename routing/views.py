from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import TripQuerySerializer
from .services.exceptions import RoutingError
from .services.trip_planner import plan_trip


class TripPlanView(APIView):
    """GET /api/route/?start=Chicago, IL&finish=Denver, CO

    Returns the route, the cost-optimal fuel stops and the total fuel cost.
    """

    def get(self, request):
        query = TripQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        try:
            trip = plan_trip(data["start"], data["finish"])
        except RoutingError as exc:
            return Response({"error": str(exc)}, status=exc.status_code)

        if not data["include_route"]:
            trip.pop("route")
        params = urlencode({"start": data["start"], "finish": data["finish"]})
        trip["map_url"] = request.build_absolute_uri(f"{reverse('trip-map')}?{params}")
        return Response(trip)


def trip_map(request):
    """GET /api/route/map/?start=...&finish=...  -> interactive Leaflet map (HTML).

    Reuses the cached route from the JSON endpoint, so it costs no extra API call.
    """
    query = TripQuerySerializer(data=request.GET)
    if not query.is_valid():
        return render(request, "routing/map.html", {"error": query.errors}, status=400)
    try:
        trip = plan_trip(query.validated_data["start"], query.validated_data["finish"])
    except RoutingError as exc:
        return render(request, "routing/map.html", {"error": str(exc)}, status=exc.status_code)
    return render(request, "routing/map.html", {"trip": trip})
