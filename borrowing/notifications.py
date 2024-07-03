import logging
from datetime import datetime, timedelta

from borrowing.management.commands.send_notification import notification

from borrowing.models import Borrowing

logger = logging.getLogger(__name__)


def get_overdue_borrowings():
    tomorrow = datetime.now().date() + timedelta(days=1)
    queryset = Borrowing.objects.filter(
            actual_return_date__isnull=True,
            expected_return_date__lte=tomorrow
    )
    return queryset


def send_overdue_borrowing_notification():
    borrowings = get_overdue_borrowings()
    if not borrowings:
        notification("There are no overdue borrowings today.")

    for borrowing in borrowings:
        logger.info(f"Creating message for borrowing with id: {borrowing.id}")
        message = f"The expiration date of your borrowing is " \
                  f"{borrowing.expected_return_date}.\n" \
                  f"Please return the book '{borrowing.book.title}' " \
                  f"by that time."
        notification(message)
        logger.info(f"The message has been sent successfully.")
