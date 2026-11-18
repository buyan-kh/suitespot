"""US3.1, task 3.1.2 — Payment confirmation endpoint.

POST /reservations/{id}/confirm
  Marks a pending reservation as confirmed once a successful charge is reported.
  The caller (front-end or webhook) supplies the amount, payment method, and the
  provider's transaction ID.  The service layer re-checks the amount so the
  charged amount always matches what the guest was shown.

Intentionally simple: this project uses a mock / sandbox payment provider, so
there is no real Stripe/Braintree SDK call here.  The front-end calls the
provider directly, gets a transaction_id back, and then POSTs it here to
finalise the booking.  Real-money integration (3.1.7) lives in a separate task.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.services.booking_confirmation import (
    AmountMismatch,
    Confirmation,
    DuplicatePayment,
    NotPayable,
    ReservationNotFound,
    confirm_booking,
)

router = APIRouter(prefix="/reservations", tags=["payment"])


class ConfirmPaymentBody(BaseModel):
    amount: float = Field(..., gt=0, description="Amount charged in dollars (must match reservation total).")
    payment_method: str = Field(..., min_length=1, max_length=50, description="e.g. 'card', 'paypal'")
    transaction_id: str = Field(..., min_length=1, max_length=255, description="Provider-issued transaction ID.")


@router.post("/{reservation_id}/confirm")
def confirm_payment(
    reservation_id: str,
    body: ConfirmPaymentBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm a reservation after a successful payment charge.

    - **200** — reservation is now confirmed (or was already confirmed by a
      previous identical request — idempotent on the same transaction_id).
    - **404** — reservation not found or belongs to a different user.
    - **409** — reservation is not in a payable state, amount doesn't match,
      or the transaction ID is already used by another reservation.
    - **422** — missing / invalid request body fields.
    """
    try:
        result: Confirmation = confirm_booking(
            db,
            reservation_id=reservation_id,
            amount=body.amount,
            payment_method=body.payment_method,
            transaction_id=body.transaction_id,
        )
    except ReservationNotFound:
        raise HTTPException(404, "Reservation not found.")
    except AmountMismatch as exc:
        raise HTTPException(409, {
            "code": "amount_mismatch",
            "message": "The charged amount does not match the reservation total.",
            "expected": float(exc.expected),
            "charged": float(exc.charged),
        })
    except DuplicatePayment as exc:
        raise HTTPException(409, {"code": "duplicate_payment", "message": str(exc)})
    except NotPayable as exc:
        raise HTTPException(409, {"code": "not_payable", "message": str(exc)})

    res = result.reservation
    pay = result.payment
    return {
        "reservation_id": res.id,
        "status": res.status,
        "already_confirmed": result.already_confirmed,
        "payment": {
            "transaction_id": pay.transaction_id,
            "amount": float(pay.amount),
            "payment_method": pay.payment_method,
            "paid_at": pay.paid_at.isoformat() if pay.paid_at else None,
        },
    }
