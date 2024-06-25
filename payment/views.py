import stripe

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status, generics, viewsets

from payment.models import Payment
from payment.payment_session import (
    create_stripe_session,
    send_payment_notification,
)
from payment.serializers import (
    PaymentSerializer,
    PaymentListSerializer,
    PaymentDetailSerializer,
)


class PaymentViewSet(
    generics.ListAPIView,
    generics.RetrieveAPIView,
    generics.CreateAPIView,
    viewsets.GenericViewSet
):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return PaymentListSerializer
        if self.action == "retrieve":
            return PaymentDetailSerializer
        return PaymentSerializer

    def get_queryset(self):
        if self.request.user.is_staff:
            return super().get_queryset()
        return super().get_queryset().filter(borrowing__user=self.request.user)

    @action(
        methods=["GET"],
        detail=False,
        url_path="payment-success",
        url_name="success",
    )
    def payment_success(self, request: Request):
        session_id = request.query_params.get("session_id")
        payment = Payment.objects.get(session_id=session_id)

        session = stripe.checkout.Session.retrieve(session_id)

        if session.payment_status == "paid":
            serializer = PaymentDetailSerializer(
                payment, data={"status": "PAID"}, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            send_payment_notification(payment)

            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    @action(
        methods=["GET"],
        detail=False,
        url_path="payment-cancel",
        url_name="cancel",
    )
    def payment_cancel(self, request: Request):
        session_id = request.query_params.get("session_id")
        payment = Payment.objects.get(session_id=session_id)
        serializer = PaymentSerializer(payment)
        data = {
            "message": "You can make a payment during the next 16 hours.",
            **serializer.data
        }
        return Response(data=data, status=status.HTTP_200_OK)

    @action(
        methods=["POST"],
        detail=True,
        url_path="recreate-session",
        url_name="recreate",
    )
    def recreate_payment_session(self, request, pk=None):
        payment = self.get_object()
        borrowing = payment.borrowing

        if payment.status == "EXPIRED":
            new_payment_session = create_stripe_session(
                borrowing=borrowing, request=self.request
            )

            payment.status = "PENDING"
            payment.session_id = new_payment_session.id
            payment.session_url = new_payment_session.url

            payment.save()

            return Response({"status": "Session has been recreated"})

        return Response({"status": "Session is still active"})
