from rest_framework import serializers

from payment.models import Payment


class PaymentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "borrowing",
            "money_to_pay"
        )


class PaymentListSerializer(PaymentSerializer):

    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "money_to_pay"
        )


class PaymentDetailSerializer(PaymentSerializer):
    borrowing = serializers.StringRelatedField(
        many=False, read_only=True
    )

    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "borrowing",
            "session_url",
            "session_id",
            "money_to_pay"
        )
