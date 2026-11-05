"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/Button";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

interface BookingWidgetProps {
  hotelId: string;
  basePrice: number;
}

export default function BookingWidget({ hotelId, basePrice }: BookingWidgetProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [checkIn, setCheckIn] = useState(searchParams.get("checkIn") || "");
  const [checkOut, setCheckOut] = useState(searchParams.get("checkOut") || "");
  const [adults, setAdults] = useState(Number(searchParams.get("adults")) || 1);
  const [children, setChildren] = useState(Number(searchParams.get("children")) || 0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const nights = checkIn && checkOut 
    ? Math.max(1, Math.ceil((new Date(checkOut).getTime() - new Date(checkIn).getTime()) / (1000 * 60 * 60 * 24))) 
    : 1;
  const totalPrice = nights * basePrice;
  const totalGuests = adults + children;

  const handleBooking = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!checkIn || !checkOut) {
      setError("Please select both check-in and check-out dates.");
      return;
    }

    if (new Date(checkIn) >= new Date(checkOut)) {
      setError("Check-out date must be after check-in date.");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch(`${API}/reservations`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          hotel_id: hotelId,
          check_in: checkIn,
          check_out: checkOut,
          guests: totalGuests,
          adults,
          children
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Selected room is unavailable for these dates or booking failed.");
      }

      const reservation = await res.json();
      router.push(`/checkout?reservationId=${reservation.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred while booking.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-surface border border-line rounded-card p-6 shadow-sm space-y-6 sticky top-24">
      <div className="flex justify-between items-baseline">
        <div>
          <span className="text-2xl font-bold text-ink">${basePrice}</span>
          <span className="text-sm text-muted"> / night</span>
        </div>
        <div className="text-xs font-semibold text-accent uppercase tracking-wider">
          Best Rate Guaranteed
        </div>
      </div>

      {error && (
        <div className="p-3 text-sm text-danger bg-danger-soft border border-danger/20 rounded-control">
          {error}
        </div>
      )}

      <form onSubmit={handleBooking} className="space-y-4">
        {/* Date Pickers */}
        <div className="grid grid-cols-2 gap-2 border border-line rounded-control p-2 bg-canvas">
          <div className="space-y-1 px-2 py-1">
            <label className="block text-[10px] font-bold text-muted uppercase tracking-wider">Check-in</label>
            <input 
              type="date" 
              value={checkIn}
              onChange={(e) => setCheckIn(e.target.value)}
              className="w-full bg-transparent text-sm font-semibold text-ink focus:outline-none"
              required 
            />
          </div>
          <div className="space-y-1 px-2 py-1 border-l border-line">
            <label className="block text-[10px] font-bold text-muted uppercase tracking-wider">Check-out</label>
            <input 
              type="date" 
              value={checkOut}
              onChange={(e) => setCheckOut(e.target.value)}
              className="w-full bg-transparent text-sm font-semibold text-ink focus:outline-none"
              required 
            />
          </div>
        </div>

        {/* Guests Selector */}
        <div className="border border-line rounded-control p-3 bg-canvas space-y-3">
          <label className="block text-[10px] font-bold text-muted uppercase tracking-wider">Guests</label>
          <div className="flex justify-between items-center text-sm">
            <span className="text-ink font-medium">Adults</span>
            <div className="flex items-center gap-3">
              <button 
                type="button" 
                onClick={() => setAdults(Math.max(1, adults - 1))}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted"
              >-</button>
              <span className="font-bold w-4 text-center">{adults}</span>
              <button 
                type="button" 
                onClick={() => setAdults(adults + 1)}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted"
              >+</button>
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
                onClick={() => setChildren(Math.max(0, children - 1))}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted"
              >-</button>
              <span className="font-bold w-4 text-center">{children}</span>
              <button 
                type="button" 
                onClick={() => setChildren(children + 1)}
                className="w-8 h-8 rounded-full border border-line flex items-center justify-center hover:bg-surface-muted"
              >+</button>
            </div>
          </div>
        </div>

        {/* Price Breakdown Preview */}
        <div className="space-y-2 pt-2 text-sm">
          <div className="flex justify-between text-muted">
            <span>${basePrice} × {nights} night{nights > 1 ? "s" : ""}</span>
            <span>${totalPrice}</span>
          </div>
          <div className="flex justify-between font-bold text-ink text-base pt-2 border-t border-line">
            <span>Total before taxes</span>
            <span>${totalPrice}</span>
          </div>
        </div>

        <Button type="submit" disabled={loading} className="w-full h-12 font-bold text-base mt-2">
          {loading ? "Checking availability..." : "Reserve & Continue"}
        </Button>
      </form>
    </div>
  );
}