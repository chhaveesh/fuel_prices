from django.db import models


class City(models.Model):
    """US city with coordinates. Used to geocode fuel stations and resolve
    start/finish inputs offline, so no external geocoding API is needed."""

    name = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    # Normalized "city|ST" key for fast exact lookups (e.g. "saint louis|MO").
    key = models.CharField(max_length=120, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        verbose_name_plural = "cities"

    def __str__(self):
        return f"{self.name}, {self.state}"


class FuelStation(models.Model):
    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=6, decimal_places=3)
    # Approximated by city centroid: the source data has highway/exit
    # addresses only, which aren't reliably geocodable.
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"
