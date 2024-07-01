import stripe

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse

from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from book.models import Book
from borrowing.models import Borrowing
from payment.models import Payment
from payment.serializers import (
    PaymentSerializer,
    PaymentListSerializer,
    PaymentDetailSerializer,
)

PAYMENT_URL = reverse("payment:payment-list")
SUCCESS_URL = reverse("payment:payment-success")
CANCEL_URL = reverse("payment:payment-cancel")


def sample_book(**kwargs):
    defaults = {
        "title": "Sample book 1",
        "author": "Test Author 1",
        "cover": "S",
        "inventory": 5,
        "daily_fee": 10.0
    }
    defaults.update(kwargs)

    return Book.objects.create(**defaults)


def sample_borrowing(**kwargs):
    book = sample_book()
    user = kwargs.get("user")

    defaults = {
        "expected_return_date": datetime.now().date() + timedelta(days=15),
        "book": book,
        "user": user
    }
    defaults.update(kwargs)

    return Borrowing.objects.create(**defaults)


def sample_payment(**kwargs):
    borrowing = kwargs.get("borrowing")

    defaults = {
        "borrowing": borrowing
    }
    defaults.update(kwargs)

    return Payment.objects.create(**defaults)


def detail_url(payment_id):
    return reverse("payment:payment-detail", args=[payment_id])


class UnauthenticatedPaymentApiTests(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_auth_required(self):
        resp = self.client.get(PAYMENT_URL)
        self.assertEquals(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticatedPaymentApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user_1 = get_user_model().objects.create_user(
            "test1@test.com",
            "testpass1"
        )
        self.user_2 = get_user_model().objects.create_user(
            "test2@test.com",
            "testpass2"
        )
        self.user_3 = get_user_model().objects.create_user(
            "test3@test.com",
            "testpass3"
        )

        refresh = RefreshToken.for_user(self.user_1)
        self.token = refresh.access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.book_1 = Book.objects.create(
            title="Sample book 2",
            author="Test Author 2",
            cover="S",
            inventory=5,
            daily_fee=10.0
        )
        self.book_2 = Book.objects.create(
            title="Sample book 3",
            author="Test Author 3",
            cover="H",
            inventory=6,
            daily_fee=15.0
        )
        self.book_3 = Book.objects.create(
            title="Sample book 4",
            author="Test Author 4",
            cover="S",
            inventory=7,
            daily_fee=20.0
        )

        self.borrowing_1 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=10),
            book=self.book_1,
            user=self.user_1
        )

        self.borrowing_2 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=15),
            book=self.book_2,
            user=self.user_1
        )
        self.borrowing_3 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=20),
            book=self.book_2,
            user=self.user_2
        )
        self.borrowing_4 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=25),
            book=self.book_3,
            user=self.user_3
        )

        self.factory = RequestFactory()

    def test_list_payments(self):
        sample_payment(
            borrowing=self.borrowing_1
        )
        sample_payment(
            borrowing=self.borrowing_2
        )

        resp = self.client.get(PAYMENT_URL)

        payments_only_auth_user = Payment.objects.filter(
            borrowing__user=self.user_1
        )

        serializer = PaymentListSerializer(payments_only_auth_user, many=True)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, serializer.data)

    def test_user_can_see_only_his_own_payments(self):
        own_payment = sample_payment(
            borrowing=self.borrowing_1
        )
        another_user_payment = sample_payment(
            borrowing=self.borrowing_3
        )

        own_url_payment = detail_url(own_payment.id)
        another_user_url_payment = detail_url(another_user_payment.id)

        resp_own = self.client.get(own_url_payment)
        resp_another_user = self.client.get(another_user_url_payment)

        serializer_own = PaymentDetailSerializer(own_payment)

        self.assertEquals(resp_own.data, serializer_own.data)
        self.assertEquals(
            resp_another_user.status_code,
            status.HTTP_404_NOT_FOUND
        )

    @patch("payment.payment_session.send_payment_notification")
    @patch("stripe.checkout.Session.retrieve")
    def test_payment_success(
        self,
        mock_session_retrieve,
        mock_send_notification
    ):
        price_data = stripe.Price.create(
            unit_amount=1200,
            currency="usd",
            product_data={
                "name": f"Payment for borrowing of {self.book_1.title}",
            }
        )
        stripe_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": price_data.id,
                    "quantity": 1
                }
            ],
            mode="payment",
            success_url="http://localhost:8000/success/",
            cancel_url="http://localhost:8000/cancel/"
        )

        payment = sample_payment(
            borrowing=self.borrowing_1
        )

        payment.session_id = stripe_session.id
        payment.session_url = stripe_session.url
        payment.money_to_pay = stripe_session.amount_total
        payment.expires_at = datetime.fromtimestamp(stripe_session.expires_at)

        payment.save()

        mock_session_retrieve.return_value = MagicMock(payment_status="paid")

        url_success_payment = (
                SUCCESS_URL + f"?session_id={payment.session_id}"
        )

        resp = self.client.get(url_success_payment)

        payment = Payment.objects.get(session_id=payment.session_id)

        serializer = PaymentDetailSerializer(payment)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, serializer.data)
        self.assertEquals(payment.status, "PAID")

    def test_payment_cancel(self):
        price_data = stripe.Price.create(
            unit_amount=1200,
            currency="usd",
            product_data={
                "name": f"Payment for borrowing of {self.book_1.title}",
            }
        )
        stripe_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": price_data.id,
                    "quantity": 1
                }
            ],
            mode="payment",
            success_url="http://localhost:8000/success/",
            cancel_url="http://localhost:8000/cancel/"
        )

        payment = sample_payment(
            borrowing=self.borrowing_1
        )

        payment.session_id = stripe_session.id
        payment.session_url = stripe_session.url
        payment.money_to_pay = stripe_session.amount_total
        payment.expires_at = datetime.fromtimestamp(stripe_session.expires_at)

        payment.save()

        url_cancel_payment = CANCEL_URL + f"?session_id={payment.session_id}"

        resp = self.client.get(url_cancel_payment)
        serializer = PaymentSerializer(payment)

        self.assertEquals(
            resp.data["message"],
            "You can make a payment during the next 16 hours."
        )

        self.assertEquals(resp.data["id"], serializer.data["id"])
        self.assertEquals(resp.data["status"], serializer.data["status"])
        self.assertEquals(resp.data["borrowing"], serializer.data["borrowing"])
        self.assertEquals(
            resp.data["money_to_pay"], serializer.data["money_to_pay"]
        )

    @patch("celery.app.task.Task.delay", return_value=1)
    @patch("celery.app.task.Task.apply_async", return_value=1)
    def test_recreate_payment_session(self, *args, **kwargs):
        borrowing = sample_borrowing(user=self.user_1)

        price_data = stripe.Price.create(
            unit_amount=1200,
            currency="usd",
            product_data={
                "name": f"Payment for borrowing of {self.book_1.title}",
            }
        )
        stripe_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": price_data.id,
                    "quantity": 1
                }
            ],
            mode="payment",
            success_url="http://localhost:8000/success/",
            cancel_url="http://localhost:8000/cancel/"
        )

        payment = sample_payment(
            borrowing=borrowing
        )

        payment.session_id = stripe_session.id
        payment.session_url = stripe_session.url
        payment.money_to_pay = stripe_session.amount_total
        payment.expires_at = datetime.fromtimestamp(stripe_session.expires_at)

        payment.status = "EXPIRED"

        payment.save()

        url = reverse("payment:payment-recreate", args=[payment.id])

        request = self.factory.post(url)
        request.user = self.user_1

        resp = self.client.post(url)

        payment.refresh_from_db()

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(payment.session_id, stripe_session.id)
        self.assertNotEqual(payment.session_url, stripe_session.url)
        self.assertEqual(payment.status, "PENDING")
        self.assertEqual(resp.data["status"], "Session has been recreated")


class AdminPaymentApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user_1 = get_user_model().objects.create_user(
            "admin@admin.com", "testpass", is_staff=True
        )
        self.user_2 = get_user_model().objects.create_user(
            "test2@test.com",
            "testpass2"
        )
        self.user_3 = get_user_model().objects.create_user(
            "test3@test.com",
            "testpass3"
        )

        refresh = RefreshToken.for_user(self.user_1)
        self.token = refresh.access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_admin_can_see_all_payments(self):
        borrowing_1 = sample_borrowing(user=self.user_1)
        borrowing_2 = sample_borrowing(user=self.user_2)
        borrowing_3 = sample_borrowing(user=self.user_3)

        payment_1 = sample_payment(borrowing=borrowing_1)
        payment_2 = sample_payment(borrowing=borrowing_2)
        payment_3 = sample_payment(borrowing=borrowing_3)

        resp = self.client.get(PAYMENT_URL)

        serializer_1 = PaymentListSerializer(payment_1)
        serializer_2 = PaymentListSerializer(payment_2)
        serializer_3 = PaymentListSerializer(payment_3)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(serializer_1.data, resp.data)
        self.assertIn(serializer_2.data, resp.data)
        self.assertIn(serializer_3.data, resp.data)
