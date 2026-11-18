"""Provider boundary. Manual confirmation is the only enabled payment recorder."""

from typing import Protocol
from fastapi import HTTPException
from .db import add
from .models import Payment


class PaymentRecorder(Protocol):
    def record(self, db, bill, staff, data): ...


class ManualRecorder:
    def record(self, db, bill, staff, data):
        if not data.confirmed or not data.method:
            raise HTTPException(
                422, "Confirm receipt and select the actual payment method."
            )
        return add(
            db,
            Payment,
            tenant=bill.tenant,
            bill_id=bill.id,
            staff_id=staff.id,
            amount=bill.total,
            method=data.method,
            reference=data.reference,
        )


manual_payments: PaymentRecorder = ManualRecorder()
