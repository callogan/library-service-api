from datetime import datetime

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from borrowing.models import Borrowing
from book.serializers import BookSerializer
from payment.payment_session import create_payment


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

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.context["request"].user
        Borrowing.validate_inventory(
            attrs["book"],
            ValidationError
        )
        Borrowing.validate_pending_borrowings(user, ValidationError)
        return data

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


class BorrowingReturnBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Borrowing
        fields = (
            "id",
            "borrow_date",
            "expected_return_date",
            "actual_return_date"
        )

    def validate(self, attrs):
        borrowing = self.instance
        if borrowing.actual_return_date is not None:
            raise ValidationError(detail="Book has been already returned.")
        return super().validate(attrs=attrs)

    @transaction.atomic
    def update(self, instance, validated_data):
        book = instance.book
        instance.actual_return_date = datetime.now().date()
        instance.save()
        book.inventory += 1
        book.save()

        request = self.context.get("request")
        borrowing = instance
        create_payment(borrowing, request)

        return instance
