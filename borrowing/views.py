from datetime import datetime

from django.db import transaction
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from borrowing.models import Borrowing
from borrowing.serializers import (
    BorrowingSerializer,
    BorrowingCreateSerializer,
    BorrowingListSerializer,
    BorrowingDetailSerializer,
    BorrowingReturnBookSerializer,
)
from borrowing.tasks import overdue_borrowing_notifications


class BorrowingViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet
):
    queryset = Borrowing.objects.all()
    serializer_class = BorrowingSerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        overdue_borrowing_notifications.delay()
        return response

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @staticmethod
    def _params_to_ints(qs):
        """Converts a list of string IDs to a list of integers"""
        return [int(str_id) for str_id in qs.split(",")]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ("list", "retrieve") and not self.request.user.is_staff:
            return queryset.filter(user_id=self.request.user.id)

        user = self.request.query_params.get("user")
        is_active = self.request.query_params.get("is_active", "").lower()

        if is_active == "true":
            queryset = queryset.filter(
                actual_return_date__isnull=True
            )

        if is_active == "false":
            queryset = queryset.filter(
                actual_return_date__isnull=False
            )

        if self.request.user.is_staff:
            if user:
                user_id = self._params_to_ints(user)
                queryset = queryset.filter(user_id__in=user_id)

        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return BorrowingListSerializer
        if self.action == "retrieve":
            return BorrowingDetailSerializer
        if self.action == "create":
            return BorrowingCreateSerializer
        if self.action == "return_book":
            return BorrowingReturnBookSerializer
        return self.serializer_class

    @transaction.atomic
    @action(
        methods=["PATCH"],
        detail=True,
        url_path="return-book",
        serializer_class=BorrowingReturnBookSerializer,
    )
    def return_book(self, request, pk=None):
        """Endpoint for returning borrowed book"""
        borrowing = self.get_object()
        actual_return_date = datetime.now().date()

        serializer_update = BorrowingReturnBookSerializer(
            borrowing,
            context={"request": self.request},
            data={"actual_return_date": actual_return_date},
            partial=True,
        )
        serializer_update.is_valid(raise_exception=True)
        serializer_update.save()
        return Response({"status": "book returned"})
