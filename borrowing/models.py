from django.db import models
from rest_framework.generics import get_object_or_404

from book.models import Book
from borrowing.management.commands.send_notification import notification
from library_service import settings


class Borrowing(models.Model):

    borrow_date = models.DateField(auto_now_add=True)
    expected_return_date = models.DateField()
    actual_return_date = models.DateField(null=True, blank=True)
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="borrowings"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="borrowings"
    )

    class Meta:
        ordering = ("borrow_date",)

    def __str__(self):
        return f"{self.book.title} borrowed by {self.user}"

    def save(self, *args, **kwargs):
        book = get_object_or_404(Book, pk=self.book.id)
        message = (
            f"You have borrowed the book:\n'{book.title}'."
            f"\nExpected return date:"
            f"\n{self.expected_return_date}\n"
            f"Rental fee per day:\n"
            f"{book.daily_fee} $"
        )
        if self.pk is None:
            notification(message)
        super().save(*args, **kwargs)

    @staticmethod
    def validate_inventory(book, error_to_raise):
        if book.inventory < 1:
            raise error_to_raise("There are no books in inventory to borrow.")
