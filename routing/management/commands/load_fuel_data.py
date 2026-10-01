"""Load US cities and fuel stations into the database.

Run once after migrating:  python manage.py load_fuel_data

Cleaning steps for the fuel price CSV:
  * drop Canadian stations (the API is USA-only)
  * strip stray whitespace from city/state
  * collapse duplicate OPIS IDs, keeping the cheapest price
  * geocode each station to its city centroid (offline lookup)
"""
import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from routing.models import City, FuelStation
from routing.utils import city_key

CANADIAN_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}


class Command(BaseCommand):
    help = "Load US city coordinates and fuel station prices into the database."

    def add_arguments(self, parser):
        data_dir = Path(settings.BASE_DIR) / "data"
        parser.add_argument("--cities", default=data_dir / "us_cities.csv")
        parser.add_argument("--prices", default=data_dir / "fuel_prices.csv")

    @transaction.atomic
    def handle(self, *args, **opts):
        coords = self._load_cities(opts["cities"])
        self._load_stations(opts["prices"], coords)

    def _load_cities(self, path):
        City.objects.all().delete()
        cities, coords = [], {}
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = city_key(row["CITY"], row["STATE_CODE"])
                if key in coords:  # dataset has a few same-name duplicates; keep first
                    continue
                lat, lng = float(row["LATITUDE"]), float(row["LONGITUDE"])
                coords[key] = (lat, lng)
                cities.append(City(name=row["CITY"], state=row["STATE_CODE"],
                                   key=key, latitude=lat, longitude=lng))
        City.objects.bulk_create(cities, batch_size=2000)
        self.stdout.write(f"Loaded {len(cities)} cities")
        return coords

    def _load_stations(self, path, coords):
        stations = {}  # opis_id -> FuelStation (cheapest wins)
        skipped_canada, unmatched = 0, set()
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                state = row["State"].strip().upper()
                if state in CANADIAN_PROVINCES:
                    skipped_canada += 1
                    continue
                city = row["City"].strip()
                key = city_key(city, state)
                if key not in coords:
                    unmatched.add(f"{city}, {state}")
                    continue
                opis_id = int(row["OPIS Truckstop ID"])
                price = Decimal(row["Retail Price"]).quantize(Decimal("0.001"))
                existing = stations.get(opis_id)
                if existing and existing.price <= price:
                    continue
                lat, lng = coords[key]
                stations[opis_id] = FuelStation(
                    opis_id=opis_id, name=row["Truckstop Name"].strip(),
                    address=row["Address"].strip(), city=city, state=state,
                    rack_id=int(row["Rack ID"]), price=price,
                    latitude=lat, longitude=lng,
                )

        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(stations.values(), batch_size=2000)
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(stations)} fuel stations"))
        self.stdout.write(f"Skipped {skipped_canada} Canadian rows")
        if unmatched:
            self.stdout.write(self.style.WARNING(
                f"Could not geocode {len(unmatched)} cities: {', '.join(sorted(unmatched))}"))
