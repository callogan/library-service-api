from __future__ import annotations

import os
import stripe
from rest_framework.request import Request
from rest_framework.reverse import reverse
from stripe.checkout import Session

from borrowing.models import Borrowing
from payment.models import Payment


stripe.api_key = os.environ.get("STRIPE_API_KEY")
LATE_FEE_MULTIPLIER = 2


def calculate_rental_fee_amount(borrowing: Borrowing) -> int:
    borrowing_period = (
        borrowing.expected_return_date - borrowing.borrow_date
    ).days
    pay_rate = borrowing.book.daily_fee
    return int(pay_rate * borrowing_period * 100)


def calculate_late_fee_amount(borrowing: Borrowing) -> int:
    overdue_period = (
        borrowing.actual_return_date - borrowing.expected_return_date
    ).days
    pay_rate = borrowing.book.daily_fee
    return int(pay_rate * LATE_FEE_MULTIPLIER * overdue_period * 100)


def create_payment(borrowing: Borrowing, request: Request) -> Payment | None:
    payment = Payment.objects.create(
        status="PENDING",
        borrowing=borrowing
    )

    stripe_session = create_stripe_session(borrowing, request)

    payment.session_id = stripe_session.id
    payment.session_url = stripe_session.url
    payment.money_to_pay = stripe_session.amount_total / 100

    payment.save()

    return payment


def create_stripe_session(borrowing: Borrowing, request: Request) -> Session:
    book = borrowing.book

    if (
            borrowing.actual_return_date
            and borrowing.actual_return_date > borrowing.expected_return_date
    ):

        rental_fee_amount = calculate_rental_fee_amount(borrowing)
        late_fee_amount = calculate_late_fee_amount(borrowing)
        total_amount = rental_fee_amount + late_fee_amount
        product_name = f"Payment for borrowing of {book.title}, " \
                       f"consisting of rental fee amount " \
                       f"{rental_fee_amount} and late fee amount " \
                       f"{late_fee_amount}"
    else:
        total_amount = calculate_rental_fee_amount(borrowing)
        product_name = f"Payment for borrowing of {book.title}, " \
                       f"including only rental fee amount {total_amount}"

    success_url = reverse("payment:payment-success", request=request)
    cancel_url = reverse("payment:payment-cancel", request=request)
    price_data = stripe.Price.create(
        unit_amount=total_amount,
        currency="usd",
        product_data={
            "name": product_name
        }
    )

    session = stripe.checkout.Session.create(
        line_items=[
            {
                "price": price_data.id,
                "quantity": 1
            }
        ],
        mode="payment",
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url + "?session_id={CHECKOUT_SESSION_ID}"
    )

    return session
