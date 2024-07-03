from celery import shared_task

from payment.check_expired_payments import check_expired_payments


@shared_task
def check_stripe_expired_payments():
    check_expired_payments()
