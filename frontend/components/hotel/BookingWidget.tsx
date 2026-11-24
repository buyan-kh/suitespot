"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import StayConflictNotice, {
  getStayConflict,
  type StayConflict,
} from "@/components/booking/StayConflictNotice";
import { Button } from "@/components/ui/Button";
import { authFetch, getAccessToken, getRefreshToken } from "@/lib/auth";

export type SelectedRoom = {
  id: string;
  room_number: string;
  room_type: string;
  price_per_night: number;
  max_guests: number;
  available: boolean;
};

interface BookingWidgetProps {
  room: SelectedRoom | null;
  checkIn: string;
  checkOut: string;
  adults: number;
  childrenCount: number;
  onCheckInChange: (value: string) => void;
  onCheckOutChange: (value: string) => void;
  onGuestsChange: (adults: number, children: number) => void;
}

const todayIso = () => new Date().toLocaleDateString("en-CA");

export default function BookingWidget({
  room,
  checkIn,
  checkOut,
  adults,
  childrenCount,
  onCheckInChange,
  onCheckOutChange,
  onGuestsChange,
}: BookingWidgetProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState<StayConflict | null>(null);

  const totalGuests = adults + childrenCount;
  const maxGuests = room?.max_guests ?? 10;
  const basePrice = room?.price_per_night ?? 0;

  const nights =
    checkIn && checkOut && checkOut > checkIn
      ? Math.round(
          (new Date(`${checkOut}T00:00:00`).getTime() -
            new Date(`${checkIn}T00:00:00`).getTime()) /
            (1000 * 60 * 60 * 24)
        )
      : 0;
  const subtotal = (Math.round(basePrice * 100) * nights) / 100;

  const handleBooking = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setConflict(null);

    if (!room || !room.available) {
      setError("Please select an available room first.");
      return;
    }
    if (!checkIn || !checkOut || checkOut <= checkIn) {
      setError("Check-out date must be after check-in date.");
      return;
    }
    if (totalGuests > room.max_guests) {
      setError(
        `This room accommodates up to ${room.max_guests} guest${room.max_guests === 1 ? "" : "s"}.`
      );
      return;
    }

    const query = searchParams.toString();
    const returnUrl = query ? `${pathname}?${query}` : pathname;
    if (!getAccessToken() && !getRefreshToken()) {
      router.push(`/login?next=${encodeURIComponent(returnUrl)}`);
      return;
    }

    setLoading(true);
    try {
      const res = await authFetch("/reservations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          room_id: room.id,
          check_in: checkIn,
          check_out: checkOut,
          num_guests: totalGuests,
        }),
      });

      if (res.status === 401) {
        router.push(`/login?next=${encodeURIComponent(returnUrl)}`);
        return;
      }

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const parsedConflict = getStayConflict(data);
        if (parsedConflict) {
          setConflict(parsedConflict);
          return;
        }

        const detail = data?.detail;
        if (Array.isArray(detail) && detail[0]?.msg) {
          setError(detail[0].msg);
        } else if (typeof detail === "string") {
          setError(detail);
        } else if (detail && typeof detail.message === "string") {
          setError(detail.message);
        } else {
          setError("Selected room is unavailable for these dates.");
        }
        return;
      }

      router.push(`/checkout?reservationId=${encodeURIComponent(data.id)}`);
    } catch {
      setError("Can't reach the server right now. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-surface border border-line rounded-card p-6 shadow-sm space-y-6 sticky top-24">
      <div className="flex justify-between items-baseline">
        <div>
          {room ? (
            <>
              <span className="text-2xl font-bold text-ink">${basePrice}</span>
              <span className="text-sm text-muted"> / night</span>
              <p className="text-xs text-muted capitalize mt-0.5">
                {room.room_type} · Room {room.room_number}
              </p>
            </>
          ) : (
            <span className="text-base font-semibold text-muted">Select a room</span>
          )}
        </div>
        <div className="text-xs font-semibold text-accent uppercase tracking-wider">
          15-min hold
        </div>
      </div>

      {conflict && <StayConflictNotice conflict={conflict} />}

      {error && (
        <div
          role="alert"
          className="p-3 text-sm text-danger bg-danger-soft border border-danger/20 rounded-control"
        >
          <p>{error}</p>
        </div>
      )}

      <form onSubmit={handleBooking} className="space-y-4">
        {/* Date Pickers */}
        <div className="grid grid-cols-2 gap-2 border border-line rounded-control p-2 bg-canvas">
          <div className="space-y-1 px-2 py-1">
            <label
              htmlFor="widget-checkin"
              className="block text-[10px] font-bold text-muted uppercase tracking-wider"
            >
              Check-in
            </label>
            <input
              id="widget-checkin"
              type="date"
              min={todayIso()}
              value={checkIn}
              onChange={(e) => onCheckInChange(e.target.value)}
              className="w-full bg-transparent text-sm font-semibold text-ink focus:outline-none"
              required
            />
          </div>
          <div className="space-y-1 px-2 py-1 border-l border-line">
            <label
              htmlFor="widget-checkout"
              className="block text-[10px] font-bold text-muted uppercase tracking-wider"
            >
              Check-out
            </label>
            <input
              id="widget-checkout"
              type="date"
              min={checkIn || todayIso()}
              value={checkOut}
              onChange={(e) => onCheckOutChange(e.target.value)}
              className="w-full bg-transparent text-sm font-semibold text-ink focus:outline-none"
              required
            />
          </div>
        </div>

        {/* Guests Selector */}
        <div className="border border-line rounded-control p-3 bg-canvas space-y-3">
          <span className="block text-[10px] font-bold text-muted uppercase tracking-wider">
            Guests (max {maxGuests})
          </span>
          <div className="flex justify-between items-center text-sm">
            <span className="text-ink font-medium">Adults</span>
            <div className="flex items-center gap-3">
              <button
                type="button"
                aria-label="Decrease adults"
                disabled={adults <= 1}
                onClick={() => onGuestsChange(Math.max(1, adults - 1), childrenCount)}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted disabled:opacity-40 cursor-pointer"
              >
                -
              </button>
              <span className="font-bold w-4 text-center">{adults}</span>
              <button
                type="button"
                aria-label="Increase adults"
                disabled={totalGuests >= maxGuests}
                onClick={() => onGuestsChange(adults + 1, childrenCount)}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted disabled:opacity-40 cursor-pointer"
              >
                +
              </button>
            </div>
          </div>
          <div className="flex justify-between items-center text-sm pt-2 border-t border-line/50">
            <div>
              <span className="text-ink font-medium">Children</span>
              <span className="block text-xs text-muted">Ages 0–17</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                aria-label="Decrease children"
                disabled={childrenCount <= 0}
                onClick={() => onGuestsChange(adults, Math.max(0, childrenCount - 1))}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted disabled:opacity-40 cursor-pointer"
              >
                -
              </button>
              <span className="font-bold w-4 text-center">{childrenCount}</span>
              <button
                type="button"
                aria-label="Increase children"
                disabled={totalGuests >= maxGuests}
                onClick={() => onGuestsChange(adults, childrenCount + 1)}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted disabled:opacity-40 cursor-pointer"
              >
                +
              </button>
            </div>
          </div>
        </div>

        {/* Price Breakdown Preview */}
        {room && nights > 0 && (
          <div className="space-y-2 pt-2 text-sm">
            <div className="flex justify-between text-muted">
              <span>
                ${basePrice} × {nights} night{nights > 1 ? "s" : ""}
              </span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between font-bold text-ink text-base pt-2 border-t border-line">
              <span>Room subtotal</span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
          </div>
        )}

        <Button
          type="submit"
          disabled={loading || !room || !room.available || nights <= 0}
          className="w-full h-12 font-bold text-base mt-2"
        >
          {loading ? "Reserving room..." : "Reserve & Continue"}
        </Button>
      </form>
    </div>
  );
}