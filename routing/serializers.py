from rest_framework import serializers


class TripQuerySerializer(serializers.Serializer):
    start = serializers.CharField(max_length=100, help_text="'City, ST' or 'lat,lng'")
    finish = serializers.CharField(max_length=100, help_text="'City, ST' or 'lat,lng'")
    include_route = serializers.BooleanField(
        required=False, default=True, help_text="Include route geometry (GeoJSON) in the response.")
