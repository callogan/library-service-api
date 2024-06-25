from django.core.validators import MinValueValidator
from django.db import models

from borrowing.models import Borrowing


class Payment(models.Model):
    STATUS_CHOICE = [
        ("PENDING", "Pending"),
        ("PAID", "Paid")
    ]

    status = models.CharField(
        max_length=7,
        choices=STATUS_CHOICE,
        default="PENDING"
    )
    borrowing = models.ForeignKey(
        Borrowing,
        on_delete=models.CASCADE,
        related_name="payments"
    )
    session_url = models.TextField(
        max_length=450,
        null=True,
        blank=True,
        unique=True
    )
    session_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True
    )
    money_to_pay = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    def __str__(self) -> str:
        return f"{self.status} ({self.money_to_pay}USD)"
