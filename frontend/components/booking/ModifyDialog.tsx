"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { authFetch } from "@/lib/auth";
import type { BookingCardData } from "@/components/bookings/BookingCard";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const todayIso = () => new Date().toLocaleDateString("en-CA");

type HotelRoom = {
  id: string;
  room_number: string;
  room_type: string;
  price_per_night: number;
  max_guests: number;
};

type QuoteResult = {
  current: { total: number; nights: number };
  proposed: { total: number; nights: number };
  difference: number;
  amount_paid: number;
  balance_due: number;
  refund_due: number;
  changed: boolean;
};

type ModifyDialogProps = {
  open: boolean;
  booking: BookingCardData | null;
  onClose: () => void;
  onModified: (bookingId: string, hotelName: string) => void;
};

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

function extractError(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  if (typeof detail === "string") return detail;
  return fallback;
}

export default function ModifyDialog({ open, booking, onClose, onModified }: ModifyDialogProps) {
  if (!open || !booking) return null;
  return <ModifyDialogBody booking={booking} onClose={onClose} onModified={onModified} />;
}

function ModifyDialogBody({
  booking,
  onClose,
  onModified,
}: {
  booking: BookingCardData;
  onClose: () => void;
  onModified: (bookingId: string, hotelName: string) => void;
}) {
  const [roomId, setRoomId] = useState(booking.room.id);
  const [checkIn, setCheckIn] = useState(booking.check_in);
  const [checkOut, setCheckOut] = useState(booking.check_out);
  const [numGuests, setNumGuests] = useState(booking.num_guests);

  const [rooms, setRooms] = useState<HotelRoom[]>([]);
  const [quoteEntry, setQuoteEntry] = useState<{ key: string; data: QuoteResult } | null>(null);
  const [quoteErrorEntry, setQuoteErrorEntry] = useState<{ key: string; message: string } | null>(null);
  const [quotingKey, setQuotingKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  // Fetch all rooms at this hotel so the guest can switch room types if desired
  useEffect(() => {
    const abort = new AbortController();
    fetch(`${API}/hotels/${encodeURIComponent(booking.hotel.id)}`, { signal: abort.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!abort.signal.aborted && Array.isArray(data?.rooms)) {
          setRooms(data.rooms);
        }
      })
      .catch(() => {});
    return () => abort.abort();
  }, [booking.hotel.id]);

  // Escape key & body scroll lock
  useEffect(() => {
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [submitting, onClose]);

  const hasChanges =
    roomId !== booking.room.id ||
    checkIn !== booking.check_in ||
    checkOut !== booking.check_out ||
    numGuests !== booking.num_guests;

  const dateValidationError =
    hasChanges && (!checkIn || !checkOut || checkOut <= checkIn)
      ? "Check-out date must be after check-in date."
      : "";

  const requestKey = `${roomId}|${checkIn}|${checkOut}|${numGuests}`;
  const shouldQuote = hasChanges && !dateValidationError;

  const quote = shouldQuote && quoteEntry?.key === requestKey ? quoteEntry.data : null;
  const quoting = shouldQuote && quotingKey === requestKey;
  const error =
    submitError ||
    dateValidationError ||
    (shouldQuote && quoteErrorEntry?.key === requestKey ? quoteErrorEntry.message : "");

  // Live price re-quote whenever fields differ from the current booking (Task 2.3.2 / 2.3.3)
  useEffect(() => {
    if (!shouldQuote) return;

    const abort = new AbortController();
    const timer = setTimeout(async () => {
      setQuotingKey(requestKey);
      setQuoteErrorEntry(null);
      try {
        const res = await authFetch(
          `/reservations/${encodeURIComponent(booking.id)}/quote-change`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: abort.signal,
            body: JSON.stringify({
              room_id: roomId,
              check_in: checkIn,
              check_out: checkOut,
              num_guests: numGuests,
            }),
          }
        );
        const body = await res.json().catch(() => null);
        if (abort.signal.aborted) return;

        if (!res.ok) {
          setQuoteEntry(null);
          setQuoteErrorEntry({
            key: requestKey,
            message: extractError(body, "Those changes are not available."),
          });
        } else {
          setQuoteEntry({ key: requestKey, data: body as QuoteResult });
        }
      } catch (err) {
        if (!abort.signal.aborted && (err as Error)?.name !== "AbortError") {
          setQuoteEntry(null);
          setQuoteErrorEntry({
            key: requestKey,
            message: "Could not calculate price quote right now.",
          });
        }
      } finally {
        if (!abort.signal.aborted) setQuotingKey(null);
      }
    }, 250);

    return () => {
      clearTimeout(timer);
      abort.abort();
    };
  }, [booking.id, shouldQuote, requestKey, roomId, checkIn, checkOut, numGuests]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!hasChanges || error || submitting) return;

    setSubmitting(true);
    setSubmitError("");
    try {
      const payload: Record<string, string | number> = {};
      if (roomId !== booking.room.id) payload.room_id = roomId;
      if (checkIn !== booking.check_in) payload.check_in = checkIn;
      if (checkOut !== booking.check_out) payload.check_out = checkOut;
      if (numGuests !== booking.num_guests) payload.num_guests = numGuests;

      const res = await authFetch(`/reservations/${encodeURIComponent(booking.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setSubmitError(extractError(body, "Couldn't update your reservation. Please try again."));
        return;
      }

      onModified(booking.id, booking.hotel.name);
      onClose();
    } catch {
      setSubmitError("Can't reach the server right now. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-black/50 p-4 sm:items-center"
      onClick={() => !submitting && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modify-title"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-lg rounded-card border border-line bg-surface p-6 shadow-lg space-y-5"
      >
        <button
          type="button"
          onClick={onClose}
          disabled={submitting}
          aria-label="Close"
          className="absolute right-3 top-3 rounded-full p-1.5 text-muted hover:bg-surface-muted hover:text-ink cursor-pointer"
        >
          <X aria-hidden="true" className="h-5 w-5" />
        </button>

        <div>
          <h2 id="modify-title" className="text-xl font-bold text-ink">
            Modify reservation
          </h2>
          <p className="text-sm text-muted mt-0.5">{booking.hotel.name}</p>
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          {/* Room Selector */}
          <div className="space-y-1.5">
            <label htmlFor="modify-room" className="block text-xs font-bold uppercase tracking-wider text-muted">
              Room
            </label>
            <select
              id="modify-room"
              value={roomId}
              onChange={(e) => {
                setRoomId(e.target.value);
                if (submitError) setSubmitError("");
              }}
              className="h-10 w-full rounded-control border border-line-strong bg-canvas px-3 text-sm font-medium text-ink focus:outline-none focus:ring-2 focus:ring-focus"
            >
              {rooms.length > 0 ? (
                rooms.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.room_type.charAt(0).toUpperCase() + r.room_type.slice(1)} · Room {r.room_number} (${r.price_per_night}/night · up to {r.max_guests} guests)
                  </option>
                ))
              ) : (
                <option value={booking.room.id}>
                  {booking.room.room_type} · Room {booking.room.room_number}
                </option>
              )}
            </select>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label htmlFor="modify-checkin" className="block text-xs font-bold uppercase tracking-wider text-muted">
                Check-in
              </label>
              <input
                id="modify-checkin"
                type="date"
                min={todayIso()}
                value={checkIn}
                onChange={(e) => {
                  setCheckIn(e.target.value);
                  if (submitError) setSubmitError("");
                }}
                className="h-10 w-full rounded-control border border-line-strong bg-canvas px-3 text-sm font-medium text-ink focus:outline-none focus:ring-2 focus:ring-focus"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="modify-checkout" className="block text-xs font-bold uppercase tracking-wider text-muted">
                Check-out
              </label>
              <input
                id="modify-checkout"
                type="date"
                min={checkIn || todayIso()}
                value={checkOut}
                onChange={(e) => {
                  setCheckOut(e.target.value);
                  if (submitError) setSubmitError("");
                }}
                className="h-10 w-full rounded-control border border-line-strong bg-canvas px-3 text-sm font-medium text-ink focus:outline-none focus:ring-2 focus:ring-focus"
                required
              />
            </div>
          </div>

          {/* Guests */}
          <div className="space-y-1.5">
            <label htmlFor="modify-guests" className="block text-xs font-bold uppercase tracking-wider text-muted">
              Guests
            </label>
            <input
              id="modify-guests"
              type="number"
              min={1}
              max={10}
              value={numGuests}
              onChange={(e) => {
                setNumGuests(Math.max(1, Number(e.target.value) || 1));
                if (submitError) setSubmitError("");
              }}
              className="h-10 w-full rounded-control border border-line-strong bg-canvas px-3 text-sm font-medium text-ink focus:outline-none focus:ring-2 focus:ring-focus"
              required
            />
          </div>

          {/* Error Alert */}
          {error && (
            <p role="alert" className="rounded-control bg-danger-soft border border-danger/20 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          {/* Live Price Quote Box */}
          {hasChanges && !error && (
            <div className="rounded-control border border-line bg-canvas p-3.5 text-sm space-y-1.5">
              {quoting ? (
                <p className="text-muted text-xs">Calculating updated price…</p>
              ) : quote ? (
                <>
                  <div className="flex justify-between text-muted">
                    <span>Current total ({quote.current.nights} nights)</span>
                    <span>{money.format(quote.current.total)}</span>
                  </div>
                  <div className="flex justify-between font-semibold text-ink">
                    <span>New total ({quote.proposed.nights} nights)</span>
                    <span>{money.format(quote.proposed.total)}</span>
                  </div>
                  <div className="flex justify-between border-t border-line pt-1.5 font-bold text-ink">
                    <span>
                      {quote.difference > 0
                        ? "Additional balance"
                        : quote.difference < 0
                        ? "Price reduction"
                        : "Price difference"}
                    </span>
                    <span className={quote.difference > 0 ? "text-accent" : quote.difference < 0 ? "text-success" : ""}>
                      {quote.difference > 0 ? `+${money.format(quote.difference)}` : money.format(quote.difference)}
                    </span>
                  </div>
                </>
              ) : null}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              Keep current stay
            </Button>
            <Button
              type="submit"
              disabled={!hasChanges || !!error || quoting || submitting}
            >
              {submitting ? "Saving changes…" : "Save changes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}