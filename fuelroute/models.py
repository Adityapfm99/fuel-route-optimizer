from django.db import models


class FuelStation(models.Model):
    """A truck stop with its retail fuel price, placed at its city centroid."""

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.PositiveIntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["price"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"
