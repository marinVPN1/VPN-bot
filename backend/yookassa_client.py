import yookassa
from yookassa import Payment as YookassaPayment
from yookassa.domain.models.payment_data.request import PaymentData
from yookassa.domain.models.payment_data.response import PaymentResponse
from yookassa.domain.models.amount import Amount
from yookassa.domain.models.currency import Currency
from yookassa.domain.models.confirmation.request import ConfirmationRequest
from yookassa.domain.models.confirmation.response import ConfirmationResponse
from yookassa.domain.models.confirmation_type import ConfirmationType
from typing import Dict, Optional
from loguru import logger

class YookassaClient:
    def __init__(self, shop_id: str, secret_key: str):
        self.shop_id = shop_id
        self.secret_key = secret_key
        yookassa.Configuration.configure(self.shop_id, self.secret_key)

    def create_payment(self, amount: float, currency: str = "RUB", description: str = "VPN Subscription") -> Dict:
        """Create a payment in Yookassa"""
        try:
            payment_data = PaymentData()
            payment_data.amount = Amount(amount, Currency.RUB)
            payment_data.capture = True
            payment_data.description = description
            payment_data.confirmation = ConfirmationRequest(
                type=ConfirmationType.REDIRECT,
                return_url="https://your-domain.com/payment/success"
            )

            payment = YookassaPayment.create(payment_data)
            return {
                "payment_id": payment.id,
                "status": payment.status,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "confirmation_url": payment.confirmation.confirmation_url,
                "created_at": payment.created_at
            }
        except Exception as e:
            logger.error(f"Failed to create Yookassa payment: {e}")
            raise

    def get_payment(self, payment_id: str) -> Dict:
        """Get payment information from Yookassa"""
        try:
            payment = YookassaPayment.find_one(payment_id)
            return {
                "payment_id": payment.id,
                "status": payment.status,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "paid": payment.paid,
                "created_at": payment.created_at,
                "captured_at": getattr(payment, 'captured_at', None)
            }
        except Exception as e:
            logger.error(f"Failed to get Yookassa payment {payment_id}: {e}")
            raise

    def capture_payment(self, payment_id: str) -> Dict:
        """Capture the payment"""
        try:
            payment = YookassaPayment.capture(payment_id)
            return {
                "payment_id": payment.id,
                "status": payment.status,
                "captured_at": payment.captured_at
            }
        except Exception as e:
            logger.error(f"Failed to capture Yookassa payment {payment_id}: {e}")
            raise

    def cancel_payment(self, payment_id: str) -> Dict:
        """Cancel the payment"""
        try:
            payment = YookassaPayment.cancel(payment_id)
            return {
                "payment_id": payment.id,
                "status": payment.status
            }
        except Exception as e:
            logger.error(f"Failed to cancel Yookassa payment {payment_id}: {e}")
            raise