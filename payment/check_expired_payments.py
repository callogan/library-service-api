import logging
import stripe
from datetime import datetime

from payment.models import Payment

logger = logging.getLogger(__name__)


def check_expired_payments():
    current_time = datetime.now()
    expired_payments = Payment.objects.filter(
        expires_at__lte=current_time, status="PENDING"
    )

    for payment in expired_payments:
        session_id = payment.session_id
        session = stripe.checkout.Session.retrieve(session_id)
        payment.status = "EXPIRED"
        payment.save()

        logger.info(f"Session with ID {session.id} "
                    f"and payment with ID {payment.id} are expired")
