from rest_framework import viewsets

from book.models import Book
from book.serializers import BookSerializer, BookListSerializer


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return BookListSerializer
        return self.serializer_class
