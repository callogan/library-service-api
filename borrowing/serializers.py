from django.db import transaction
from rest_framework import serializers

from borrowing.models import Borrowing
from book.serializers import BookSerializer


class BorrowingSerializer(serializers.ModelSerializer):

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user"
        )


class BorrowingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Borrowing
        fields = ("id", "borrow_date", "expected_return_date", "book", "user")

    @transaction.atomic()
    def create(self, validated_data):
        borrowing = Borrowing.objects.create(**validated_data)
        book = validated_data["book"]
        book.inventory -= 1
        book.save()

        return borrowing


class BorrowingListSerializer(serializers.ModelSerializer):
    borrow_date = serializers.DateField(format="%Y-%m-%d")
    actual_return_date = serializers.DateField(format="%Y-%m-%d")
    expected_return_date = serializers.DateField(format="%Y-%m-%d")

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user"
        )


class BorrowingDetailSerializer(BorrowingListSerializer):
    user = serializers.SlugRelatedField(
        many=False,
        read_only=True,
        slug_field="email"
    )
    book = BookSerializer(read_only=True)

    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date",
            "book",
            "user"
        )
