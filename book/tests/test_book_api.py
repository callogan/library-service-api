from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from book.models import Book
from book.serializers import BookSerializer, BookListSerializer

BOOK_URL = reverse("book:book-list")


def sample_book(**kwargs):
    defaults = {
        "title": "Test title 1",
        "author": "Test author 1",
        "cover": "S",
        "inventory": 25,
        "daily_fee": 20.0
    }
    defaults.update(kwargs)

    return Book.objects.create(**defaults)


def detail_url(book_id):
    return reverse("book:book-detail", args=[book_id])


class UnauthenticatedBooksApiTests(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.book = sample_book()

    def test_list_books_auth_not_required(self):
        resp = self.client.get(BOOK_URL)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)

    def test_create_book_not_allowed(self):
        payload = {
            "title": "Test title 2",
            "author": "Test author 2",
            "cover": "S",
            "inventory": 25,
            "daily_fee": 20.0
        }

        resp = self.client.post(BOOK_URL, payload)

        self.assertEquals(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detail_book_allowed(self):
        book = sample_book()
        url = detail_url(book.id)

        resp = self.client.get(url)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)


class AuthenticatedBookApiTests(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            "test_user@test.com",
            "testpass"
        )

        refresh = RefreshToken.for_user(self.user)
        self.token = refresh.access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.book = sample_book()

    def test_list_books(self):
        resp = self.client.get(BOOK_URL)

        books = Book.objects.all()
        serializer = BookListSerializer(books, many=True)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, serializer.data)

    def test_retrieve_book_detail(self):
        book = self.book
        url = detail_url(book.id)

        resp = self.client.get(url)

        serializer = BookSerializer(book)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, serializer.data)

    def test_book_create_not_allowed(self):
        payload = {
            "title": "Test title 2",
            "author": "Test author 2",
            "cover": "S",
            "inventory": 25,
            "daily_fee": 20.0
        }

        resp = self.client.post(BOOK_URL, payload)

        self.assertEquals(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_book_update_not_allowed(self):
        book = self.book
        url = detail_url(book.id)

        payload = {
            "title": "Test title 1 updated",
            "author": "Test author 1 updated",
            "cover": "H",
            "inventory": 28,
            "daily_fee": 30.0
        }

        resp = self.client.put(url, payload)

        self.assertEquals(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_book_delete_not_allowed(self):
        book = self.book
        url = detail_url(book.id)

        resp = self.client.delete(url)

        self.assertEquals(resp.status_code, status.HTTP_403_FORBIDDEN)


class AdminBookApiTests(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            "admin@admin.com", "testpass", is_staff=True
        )

        refresh = RefreshToken.for_user(self.user)
        self.token = refresh.access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.book = sample_book()

    def test_book_create(self):
        payload = {
            "title": "Test title 2",
            "author": "Test author 2",
            "cover": "S",
            "inventory": 60,
            "daily_fee": 50.0
        }

        resp = self.client.post(BOOK_URL, payload)

        serializer = BookSerializer(resp.data, many=False)

        self.assertEquals(resp.status_code, status.HTTP_201_CREATED)
        self.assertEquals(resp.data, serializer.data)

    def test_book_update(self):
        book = self.book
        url = detail_url(book.id)

        payload = {
            "title": "Test title 2 updated",
            "author": "Test author 2 updated",
            "cover": "S",
            "inventory": 80,
            "daily_fee": 90.0
        }

        resp = self.client.put(url, payload)

        self.assertEquals(resp.status_code, status.HTTP_200_OK)

    def test_book_delete(self):
        book = self.book
        url = detail_url(book.id)

        resp = self.client.delete(url)

        self.assertEquals(resp.status_code, status.HTTP_204_NO_CONTENT)
