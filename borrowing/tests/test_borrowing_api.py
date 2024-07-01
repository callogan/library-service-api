import stripe

from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse

from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from book.models import Book
from borrowing.models import Borrowing
from borrowing.serializers import (
    BorrowingSerializer,
    BorrowingListSerializer,
    BorrowingDetailSerializer,
)
from payment.models import Payment

BORROWING_URL = reverse("borrowing:borrowing-list")


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
    expected_return_date = kwargs.get("expected_return_date")
    user = kwargs.get("user")

    defaults = {
        "expected_return_date": expected_return_date,
        "book": book,
        "user": user
    }
    defaults.update(kwargs)

    return Borrowing.objects.create(**defaults)


def detail_url(borrowing_id):
    return reverse("borrowing:borrowing-detail", args=[borrowing_id])


def return_url(borrowing_id):
    return reverse("borrowing:return-book", args=[borrowing_id])


class UnauthenticatedBorrowingApiTests(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_auth_required(self):
        resp = self.client.get(BORROWING_URL)
        self.assertEquals(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticatedBorrowingApiTests(TestCase):
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
            inventory=2,
            daily_fee=10.0
        )
        self.book_2 = Book.objects.create(
            title="Sample book 3",
            author="Test Author 3",
            cover="S",
            inventory=5,
            daily_fee=15.0
        )
        self.book_3 = Book.objects.create(
            title="Sample book 4",
            author="Test Author 4",
            cover="S",
            inventory=4,
            daily_fee=20.0
        )
        self.book_4 = Book.objects.create(
            title="Sample book 5",
            author="Test Author 5",
            cover="S",
            inventory=3,
            daily_fee=25.0
        )

        self.borrowing_1 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=15),
            book=self.book_1,
            user=self.user_1
        )

        self.borrowing_2 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=20),
            book=self.book_2,
            user=self.user_2
        )
        self.borrowing_3 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=25),
            book=self.book_3,
            user=self.user_3
        )

        self.factory = RequestFactory()

    def test_list_borrowings(self):
        sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=10),
            user=self.user_1
        )
        sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=15),
            user=self.user_2
        )

        resp = self.client.get(BORROWING_URL)

        borrowings = Borrowing.objects.all()
        serializer = BorrowingListSerializer(borrowings, many=True)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data[0], serializer.data[0])

    def test_retrieve_own_borrowing_detail(self):
        borrowing_user1 = self.borrowing_1
        borrowing_user2 = self.borrowing_2

        borrowing_user1_url = detail_url(borrowing_user1.id)
        borrowing_user2_url = detail_url(borrowing_user2.id)

        resp_1 = self.client.get(borrowing_user1_url)
        resp_2 = self.client.get(borrowing_user2_url)

        serializer = BorrowingDetailSerializer(borrowing_user1)

        self.assertEquals(resp_1.status_code, status.HTTP_200_OK)
        self.assertEquals(resp_1.data, serializer.data)
        self.assertEquals(resp_2.status_code, status.HTTP_404_NOT_FOUND)

    @patch("celery.app.task.Task.delay", return_value=1)
    @patch("celery.app.task.Task.apply_async", return_value=1)
    def test_create_borrowing(self, *args, **kwargs):
        payload = {
            "expected_return_date": datetime.now().date() + timedelta(days=10),
            "book": self.book_1.id,
            "user": self.user_1.id
        }

        resp = self.client.post(BORROWING_URL, payload)

        self.book_1.inventory -= 1

        self.book_1.save()

        self.book_1.refresh_from_db()

        self.assertEquals(resp.status_code, status.HTTP_201_CREATED)
        self.assertEquals(self.book_1.inventory, 1)

    def test_borrowing_create_not_allowed_if_previous_not_payed(self):
        payment = Payment.objects.create(
            borrowing=self.borrowing_1
        )

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

        payment.session_id = stripe_session.id
        payment.session_url = stripe_session.url
        payment.money_to_pay = stripe_session.amount_total
        payment.expires_at = datetime.fromtimestamp(stripe_session.expires_at)

        payment.save()

        book = self.book_1
        payload = {
            "expected_return_date": datetime.now().date() + timedelta(days=30),
            "book": book.id,
            "user": self.user_1.id
        }

        resp = self.client.post(BORROWING_URL, payload)

        self.assertEquals(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEquals(
            resp.data["non_field_errors"][0],
            "You have not yet completed your paying. "
            "Please complete it before borrowing a new book."
        )

    def test_borrowing_create_not_allowed_if_zero_inventory(self):
        book = self.book_1
        sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=15),
            user=self.user_1
        )

        self.book_1.inventory -= 1

        self.book_1.save()

        sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=20),
            user=self.user_2
        )

        self.book_1.inventory -= 1

        self.book_1.save()

        payload = {
            "expected_return_date": datetime.now().date() + timedelta(days=25),
            "book": book.id,
            "user": self.user_3.id
        }

        resp = self.client.post(BORROWING_URL, payload)

        self.assertEquals(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEquals(
            resp.data["non_field_errors"][0],
            "There are no books in inventory to borrow."
        )

    def test_return_book(self):
        borrowing = self.borrowing_1

        url = detail_url(borrowing.id) + "return-book/"

        resp_1 = self.client.patch(url)
        resp_2 = self.client.patch(url)

        self.assertEquals(resp_1.status_code, status.HTTP_200_OK)
        self.assertEquals(resp_1.data["status"], "book returned")
        self.assertEquals(
            resp_2.data["non_field_errors"][0],
            "Book has been already returned."
        )

    def test_create_payment(self):
        borrowing = Borrowing.objects.create(
            expected_return_date=datetime.now().date() - timedelta(days=15),
            book=self.book_1,
            user=self.user_1
        )

        borrowing.borrow_date = datetime.now().date() - timedelta(days=20)

        borrowing.save()

        url = detail_url(borrowing.id) + "return-book/"

        self.client.patch(url)

        borrowing.actual_return_date = datetime.now().date()

        borrowing_period = (
            borrowing.expected_return_date - borrowing.borrow_date
        ).days
        overdue_period = (
            borrowing.actual_return_date - borrowing.expected_return_date
        ).days
        borrowing_amount = int(self.book_1.daily_fee * borrowing_period * 100)
        overdue_amount = int(self.book_1.daily_fee * 2 * overdue_period * 100)
        calculated_total_amount = borrowing_amount + overdue_amount

        payments = borrowing.payments.filter(status="PENDING")

        self.assertTrue(payments.exists())
        self.assertEqual(payments.count(), 1)
        payment = payments.first()
        self.assertEqual(payment.money_to_pay, calculated_total_amount / 100)

    def test_filter_borrowings_is_active_true_or_false(self):
        borrowing_1 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=10),
            book=self.book_1,
            user=self.user_1
        )
        borrowing_2 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=15),
            actual_return_date=datetime.now().date() + timedelta(days=12),
            book=self.book_2,
            user=self.user_1
        )
        borrowing_3 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=20),
            actual_return_date=datetime.now().date() + timedelta(days=18),
            book=self.book_3,
            user=self.user_1
        )
        borrowing_4 = Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=25),
            book=self.book_4,
            user=self.user_1
        )

        resp_1 = self.client.get(BORROWING_URL, payload={"is_active": "True"})
        resp_2 = self.client.get(BORROWING_URL, payload={"is_active": "False"})

        serializer1 = BorrowingSerializer(borrowing_1)
        serializer2 = BorrowingSerializer(borrowing_2)
        serializer3 = BorrowingSerializer(borrowing_3)
        serializer4 = BorrowingSerializer(borrowing_4)

        self.assertIn(serializer1.data, resp_1.data)
        self.assertIn(serializer4.data, resp_1.data)
        self.assertIn(serializer3.data, resp_2.data)
        self.assertIn(serializer2.data, resp_2.data)


class AdminBorrowingApiTests(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user_1 = get_user_model().objects.create_user(
            "admin@admin.com", "testpass1", is_staff=True
        )
        self.user_2 = get_user_model().objects.create_user(
            "test1@tests.com", "testpass2"
        )
        self.user_3 = get_user_model().objects.create_user(
            "test2@tests.com", "testpass3"
        )

        refresh = RefreshToken.for_user(self.user_1)
        self.token = refresh.access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.book = sample_book()

    def test_list_all_borrowings(self):
        sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=10),
            user=self.user_1
        )
        sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=15),
            user=self.user_2
        )

        resp = self.client.get(BORROWING_URL)

        borrowings = Borrowing.objects.all()

        serializer = BorrowingListSerializer(borrowings, many=True)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, serializer.data)

    def test_borrowing_detail_another_user(self):
        borrowing = sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=20),
            user=self.user_3
        )

        url = detail_url(borrowing.id)

        resp = self.client.get(url)

        serializer = BorrowingDetailSerializer(borrowing)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, serializer.data)

    def test_filter_borrowing_by_user_id(self):
        borrowing_1 = sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=25),
            user=self.user_2
        )
        borrowing_2 = sample_borrowing(
            expected_return_date=datetime.now().date() + timedelta(days=30),
            user=self.user_3
        )

        user = self.user_3

        resp = self.client.get(BORROWING_URL, data={"user": f"{user.id}"})

        serializer1 = BorrowingSerializer(borrowing_1)
        serializer2 = BorrowingSerializer(borrowing_2)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertIn(serializer2.data, resp.data)
        self.assertNotIn(serializer1.data, resp.data)

    def test_filter_borrowings_is_active_true_or_false(self):
        Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=10),
            book=self.book,
            user=self.user_2,
        )
        Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=15),
            actual_return_date=datetime.now().date() + timedelta(days=12),
            book=self.book,
            user=self.user_2,
        )
        Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=20),
            actual_return_date=datetime.now().date() + timedelta(days=18),
            book=self.book,
            user=self.user_3
        )
        Borrowing.objects.create(
            expected_return_date=datetime.now().date() + timedelta(days=25),
            book=self.book,
            user=self.user_3
        )

        resp_1 = self.client.get(BORROWING_URL, {"is_active": "True"})
        resp_2 = self.client.get(BORROWING_URL, {"is_active": "False"})

        borrowings_active_true = Borrowing.objects.filter(
            actual_return_date__isnull=True
        )
        borrowings_active_false = Borrowing.objects.filter(
            actual_return_date__isnull=False
        )

        serializer_active_true_borrowings = BorrowingListSerializer(
            borrowings_active_true, many=True
        )
        serializer_active_false_borrowings = BorrowingListSerializer(
            borrowings_active_false, many=True
        )

        self.assertEquals(
            resp_1.data, serializer_active_true_borrowings.data
        )
        self.assertEquals(
            resp_2.data, serializer_active_false_borrowings.data
        )
