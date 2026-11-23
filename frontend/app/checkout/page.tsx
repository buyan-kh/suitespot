'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import RequireAuth from '@/components/auth/RequireAuth';
import PriceBreakdown from '@/components/checkout/PriceBreakdown';
import CancellationPolicy from '@/components/policy/CancellationPolicy';
import { authFetch } from '@/lib/auth';
import {
  ShieldCheck,
  Lock,
  CreditCard,
  CheckCircle2,
  ArrowRight,
  Clock,
  Sparkles,
  ImageOff,
  Copy,
  Check,
  User,
  Mail,
  Phone,
} from 'lucide-react';

type ReservationCard = {
  id: string;
  status: string;
  hotel: {
    id: string;
    name: string;
    city: string;
    image?: { url: string; alt: string; sizes?: { medium?: string } } | null;
  };
  room: { id: string; room_type: string; room_number: string };
  check_in: string;
  check_out: string;
  nights: number;
  num_guests: number;
  total_price: number;
  amount_paid: number;
  hold_expires_at: string | null;
};

type ReservationDetail = {
  id: string;
  hotelName: string;
  roomTitle: string;
  imageUrl?: string;
  checkIn: string;
  checkOut: string;
  nights: number;
  nightlyRate: number;
  totalPrice: number;
  holdExpiresAt: string | null;
};

function computeSecondsLeft(expiresAt: string | null): number {
  if (!expiresAt) return 15 * 60;
  const diff = Math.floor((Date.parse(expiresAt) - Date.now()) / 1000);
  return Math.max(0, diff);
}

function CheckoutContent({ reservationId }: { reservationId: string }) {
  const [reservation, setReservation] = useState<ReservationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [paymentError, setPaymentError] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPaid, setIsPaid] = useState(false);
  const [copied, setCopied] = useState(false);
  const [timeLeft, setTimeLeft] = useState(15 * 60);

  // Guest Details State
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [specialRequests, setSpecialRequests] = useState('');

  // Payment Form State
  const [cardholderName, setCardholderName] = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvc, setCvc] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    const interval = setInterval(() => {
      setTimeLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadReservation() {
      try {
        const res = await authFetch('/me/reservations');
        if (!res.ok) throw new Error(`Could not load reservation (HTTP ${res.status}).`);
        const data = await res.json();
        if (cancelled) return;

        const all: ReservationCard[] = [
          ...(data.upcoming || []),
          ...(data.past || []),
          ...(data.cancelled || []),
        ];
        const match = all.find((r) => r.id === reservationId);
        if (!match) {
          setLoadError('This reservation hold could not be found or has already expired.');
          return;
        }
        if (match.status === 'confirmed') {
          setIsPaid(true);
        } else if (match.status === 'cancelled' || match.status === 'completed') {
          setLoadError(`This reservation is ${match.status} and cannot be paid.`);
          return;
        }

        const nights = Math.max(1, match.nights);
        const nightlyRate = Math.round((match.total_price / nights) * 100) / 100;
        setReservation({
          id: match.id,
          hotelName: match.hotel.name,
          roomTitle: `${match.room.room_type} · Room ${match.room.room_number}`,
          imageUrl: match.hotel.image?.sizes?.medium || match.hotel.image?.url,
          checkIn: match.check_in,
          checkOut: match.check_out,
          nights,
          nightlyRate,
          totalPrice: match.total_price,
          holdExpiresAt: match.hold_expires_at,
        });
        setTimeLeft(computeSecondsLeft(match.hold_expires_at));
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : 'Failed to load reservation.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadReservation();
    return () => {
      cancelled = true;
    };
  }, [reservationId]);

  const formatTime = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const s = secs % 60;
    return `${mins}:${s < 10 ? '0' : ''}${s}`;
  };

  const handleCardNumberChange = (value: string) => {
    const raw = value.replace(/\D/g, '').slice(0, 16);
    const formatted = raw.match(/.{1,4}/g)?.join(' ') || raw;
    setCardNumber(formatted);
    if (errors.cardNumber) setErrors((prev) => ({ ...prev, cardNumber: '' }));
  };

  const handleExpiryChange = (value: string) => {
    const raw = value.replace(/\D/g, '').slice(0, 4);
    let formatted = raw;
    if (raw.length >= 3) {
      formatted = `${raw.slice(0, 2)}/${raw.slice(2, 4)}`;
    }
    setExpiry(formatted);
    if (errors.expiry) setErrors((prev) => ({ ...prev, expiry: '' }));
  };

  const handleCvcChange = (value: string) => {
    const raw = value.replace(/\D/g, '').slice(0, 4);
    setCvc(raw);
    if (errors.cvc) setErrors((prev) => ({ ...prev, cvc: '' }));
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    const digitsOnly = cardNumber.replace(/\s/g, '');
    if (!fullName.trim()) next.fullName = 'Full name is required.';
    if (!email.trim() || !email.includes('@')) next.email = 'Valid email required for confirmation.';
    if (!cardholderName.trim()) next.cardholderName = 'Enter name on card.';
    if (digitsOnly.length < 15) next.cardNumber = 'Enter a valid 16-digit card number.';
    if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(expiry)) next.expiry = 'MM/YY required.';
    if (cvc.length < 3) next.cvc = 'Enter CVC.';
    if (!postalCode.trim()) next.postalCode = 'Enter ZIP code.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handlePaymentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reservation || !validate()) return;
    setPaymentError('');
    setIsProcessing(true);
    try {
      // Step 1: Verify displayed total matches backend before charging (Task 3.2.2)
      const verifyRes = await authFetch(
        `/reservations/${encodeURIComponent(reservation.id)}/verify-total`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ displayed_total: reservation.totalPrice }),
        }
      );
      if (!verifyRes.ok) {
        const vBody = await verifyRes.json().catch(() => null);
        const detail = Array.isArray(vBody?.detail) ? vBody.detail[0] : null;
        if (detail?.type === 'total_mismatch' && detail?.ctx?.expected_total) {
          const updatedTotal = Number(detail.ctx.expected_total);
          setReservation((prev) =>
            prev
              ? {
                  ...prev,
                  totalPrice: updatedTotal,
                  nightlyRate: Math.round((updatedTotal / prev.nights) * 100) / 100,
                }
              : prev
          );
          setPaymentError(
            `The stay total updated to $${updatedTotal.toFixed(2)}. Review the new total and click Pay again.`
          );
          return;
        }
        setPaymentError(detail?.msg || 'This reservation can no longer be paid.');
        return;
      }

      // Step 2: Confirm payment with backend (Task 3.1.2 / 3.1.3)
      const transactionId =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? `sandbox_${crypto.randomUUID()}`
          : `sandbox_${reservation.id}_${Date.now()}`;

      const chargeRes = await authFetch(
        `/reservations/${encodeURIComponent(reservation.id)}/confirm`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            amount: reservation.totalPrice,
            payment_method: 'card',
            transaction_id: transactionId,
          }),
        }
      );
      if (!chargeRes.ok) {
        const cBody = await chargeRes.json().catch(() => null);
        const detail = cBody?.detail;
        const msg =
          Array.isArray(detail) && detail[0]?.msg
            ? detail[0].msg
            : typeof detail === 'string'
            ? detail
            : typeof detail?.message === 'string'
            ? detail.message
            : 'Card payment was declined or could not be processed. Please check your card and retry.';
        setPaymentError(msg);
        return;
      }

      setIsPaid(true);
    } catch {
      setPaymentError("Can't reach the payment server right now. Please try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCopyCode = () => {
    if (!reservation) return;
    navigator.clipboard.writeText(reservation.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return <div className="p-12 text-center text-muted font-medium">Loading checkout details…</div>;
  }

  if (loadError || !reservation) {
    return (
      <main className="max-w-xl mx-auto px-4 py-16 text-center space-y-4">
        <p role="alert" className="rounded-control bg-danger-soft border border-danger/20 p-4 text-sm text-danger">
          {loadError || 'Reservation not found.'}
        </p>
        <Link
          href="/hotels"
          className="inline-flex items-center gap-2 bg-ink text-white font-bold text-sm px-5 py-2.5 rounded-control"
        >
          Browse hotels
        </Link>
      </main>
    );
  }

  // Confirmation View
  if (isPaid) {
    return (
      <main className="max-w-2xl mx-auto px-4 py-16 text-center space-y-6">
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
            <CheckCircle2 className="w-10 h-10 text-emerald-600" />
          </div>
        </div>
        <div className="space-y-1">
          <h1 className="text-3xl font-bold text-ink">Booking Confirmed!</h1>
          <p className="text-sm text-muted">
            {email ? (
              <>
                Confirmation sent to <span className="text-ink font-semibold">{email}</span>.
              </>
            ) : (
              'Your stay has been confirmed.'
            )}
          </p>
        </div>
        <div className="border border-line rounded-card bg-surface p-6 text-left space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-line">
            <div>
              <span className="text-xs uppercase text-muted font-bold tracking-wider">Booking Reference</span>
              <p className="text-lg font-bold text-ink tracking-wide">{reservation.id}</p>
            </div>
            <button
              type="button"
              onClick={handleCopyCode}
              className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-control border border-line bg-surface hover:bg-surface-muted transition-colors cursor-pointer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <div className="space-y-1 text-sm pb-3 border-b border-line">
            <span className="text-xs text-muted block">{reservation.hotelName}</span>
            <span className="font-semibold text-ink capitalize">{reservation.roomTitle}</span>
          </div>
          {fullName && (
            <div className="space-y-1 text-sm pb-3 border-b border-line">
              <span className="text-xs text-muted block">Guest</span>
              <span className="font-semibold text-ink">
                {fullName} {phone ? `(${phone})` : ''}
              </span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 text-sm pb-3 border-b border-line">
            <div>
              <span className="text-xs text-muted block">Check-in</span>
              <span className="font-semibold text-ink">{reservation.checkIn}</span>
            </div>
            <div>
              <span className="text-xs text-muted block">Check-out</span>
              <span className="font-semibold text-ink">{reservation.checkOut}</span>
            </div>
          </div>
          <div className="flex justify-between items-center text-sm pt-1">
            <span className="text-muted">Total Paid</span>
            <span className="text-xl font-bold text-ink">${reservation.totalPrice.toFixed(2)}</span>
          </div>
        </div>
        <div className="flex flex-wrap justify-center gap-3">
          <Link
            href="/bookings"
            className="inline-flex items-center gap-2 bg-ink hover:opacity-90 text-white font-bold text-sm px-6 py-3 rounded-control transition-all"
          >
            View My Bookings <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/hotels"
            className="inline-flex items-center gap-2 border border-line bg-surface hover:bg-surface-muted text-ink font-bold text-sm px-6 py-3 rounded-control transition-all"
          >
            Explore More Stays
          </Link>
        </div>
      </main>
    );
  }

  // Checkout View
  return (
    <main className="max-w-6xl mx-auto px-4 sm:px-8 py-10 space-y-8 text-ink">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-line pb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Confirm &amp; Pay</h1>
          <p className="text-xs text-muted font-medium mt-1">
            Provide guest information and complete payment to confirm your booking
          </p>
        </div>
        {/* 15-Minute Hold Indicator */}
        <div
          className={`inline-flex items-center gap-2 border px-3.5 py-1.5 rounded-full text-xs font-semibold self-start sm:self-auto ${
            timeLeft > 0
              ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
              : 'bg-danger-soft border-danger/20 text-danger'
          }`}
        >
          <Clock className="w-3.5 h-3.5 animate-pulse" />
          <span>{timeLeft > 0 ? `Hold reserved for ${formatTime(timeLeft)}` : 'Hold expired'}</span>
        </div>
      </div>

      {paymentError && (
        <div
          role="alert"
          className="p-4 text-sm text-danger bg-danger-soft border border-danger/20 rounded-control font-medium"
        >
          {paymentError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Guest & Payment Info (7 Cols) */}
        <div className="lg:col-span-7 space-y-6">
          <form onSubmit={handlePaymentSubmit} autoComplete="off" className="space-y-6">
            {/* 1. Guest Information Card */}
            <div className="bg-surface border border-line rounded-card p-6 space-y-5">
              <div className="flex items-center justify-between border-b border-line pb-4">
                <div className="flex items-center gap-2">
                  <User className="w-4 h-4 text-muted" />
                  <h2 className="text-sm font-bold uppercase tracking-wider text-ink">Guest Information</h2>
                </div>
                <span className="text-xs text-muted">Primary Guest</span>
              </div>

              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label htmlFor="fullName" className="text-xs font-bold text-muted uppercase tracking-wider">
                    Full Name
                  </label>
                  <input
                    id="fullName"
                    type="text"
                    value={fullName}
                    onChange={(e) => {
                      setFullName(e.target.value);
                      if (errors.fullName) setErrors((prev) => ({ ...prev, fullName: '' }));
                    }}
                    placeholder="First Last"
                    className="w-full px-3.5 py-2.5 rounded-control border border-line bg-canvas text-sm text-ink focus:outline-none focus:border-ink transition-colors"
                  />
                  {errors.fullName && <p className="text-xs text-danger font-medium">{errors.fullName}</p>}
                </div>

                <div className="grid sm:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <label htmlFor="email" className="text-xs font-bold text-muted uppercase tracking-wider">
                      Email Address
                    </label>
                    <div className="relative">
                      <input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(e) => {
                          setEmail(e.target.value);
                          if (errors.email) setErrors((prev) => ({ ...prev, email: '' }));
                        }}
                        placeholder="email@example.com"
                        className="w-full pl-3.5 pr-9 py-2.5 rounded-control border border-line bg-canvas text-sm text-ink focus:outline-none focus:border-ink transition-colors"
                      />
                      <Mail className="w-4 h-4 text-muted absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                    </div>
                    {errors.email && <p className="text-xs text-danger font-medium">{errors.email}</p>}
                  </div>

                  <div className="space-y-1.5">
                    <label htmlFor="phone" className="text-xs font-bold text-muted uppercase tracking-wider">
                      Phone Number
                    </label>
                    <div className="relative">
                      <input
                        id="phone"
                        type="tel"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="(123) 456-7890"
                        className="w-full pl-3.5 pr-9 py-2.5 rounded-control border border-line bg-canvas text-sm text-ink focus:outline-none focus:border-ink transition-colors"
                      />
                      <Phone className="w-4 h-4 text-muted absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="specialRequests" className="text-xs font-bold text-muted uppercase tracking-wider">
                    Special Requests <span className="text-[10px] lowercase text-muted font-normal">(optional)</span>
                  </label>
                  <input
                    id="specialRequests"
                    type="text"
                    value={specialRequests}
                    onChange={(e) => setSpecialRequests(e.target.value)}
                    placeholder="e.g. High floor, quiet room, late check-in"
                    className="w-full px-3.5 py-2.5 rounded-control border border-line bg-canvas text-sm text-ink focus:outline-none focus:border-ink transition-colors"
                  />
                </div>
              </div>
            </div>

            {/* 2. Payment Card Box */}
            <div className="bg-surface border border-line rounded-card p-6 space-y-5">
              <div className="flex items-center justify-between border-b border-line pb-4">
                <div className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-muted" />
                  <h2 className="text-sm font-bold uppercase tracking-wider text-ink">Payment Method</h2>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-muted">
                  <Lock className="w-3 h-3" />
                  <span>256-bit SSL encrypted</span>
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="billingName" className="text-xs font-bold text-muted uppercase tracking-wider">
                  Cardholder Name
                </label>
                <input
                  id="billingName"
                  name="billingName"
                  autoComplete="off"
                  type="text"
                  value={cardholderName}
                  onChange={(e) => {
                    setCardholderName(e.target.value);
                    if (errors.cardholderName) setErrors((prev) => ({ ...prev, cardholderName: '' }));
                  }}
                  placeholder="First Last"
                  className="w-full px-3.5 py-2.5 rounded-control border border-line bg-canvas text-sm text-ink focus:outline-none focus:border-ink transition-colors"
                />
                {errors.cardholderName && (
                  <p className="text-xs text-danger font-medium">{errors.cardholderName}</p>
                )}
              </div>

              <div className="space-y-1.5">
                <label htmlFor="accNum" className="text-xs font-bold text-muted uppercase tracking-wider">
                  Card Number
                </label>
                <div className="relative">
                  <input
                    id="accNum"
                    name="accNum"
                    autoComplete="off"
                    type="text"
                    inputMode="numeric"
                    maxLength={19}
                    value={cardNumber}
                    onChange={(e) => handleCardNumberChange(e.target.value)}
                    placeholder="1234 1234 1234 1234"
                    className="w-full pl-3.5 pr-10 py-2.5 rounded-control border border-line bg-canvas text-sm font-mono text-ink focus:outline-none focus:border-ink transition-colors"
                  />
                  <CreditCard className="w-4 h-4 text-muted absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>
                {errors.cardNumber && (
                  <p className="text-xs text-danger font-medium">{errors.cardNumber}</p>
                )}
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <label htmlFor="expiry" className="text-xs font-bold text-muted uppercase tracking-wider">
                    Expiration
                  </label>
                  <input
                    id="expiry"
                    type="text"
                    inputMode="numeric"
                    maxLength={5}
                    value={expiry}
                    onChange={(e) => handleExpiryChange(e.target.value)}
                    placeholder="MM/YY"
                    className="w-full px-3 py-2.5 text-center rounded-control border border-line bg-canvas text-sm font-mono text-ink focus:outline-none focus:border-ink transition-colors"
                  />
                  {errors.expiry && <p className="text-xs text-danger font-medium">{errors.expiry}</p>}
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="cvc" className="text-xs font-bold text-muted uppercase tracking-wider">
                    CVC
                  </label>
                  <input
                    id="cvc"
                    type="text"
                    inputMode="numeric"
                    maxLength={4}
                    value={cvc}
                    onChange={(e) => handleCvcChange(e.target.value)}
                    placeholder="123"
                    className="w-full px-3 py-2.5 text-center rounded-control border border-line bg-canvas text-sm font-mono text-ink focus:outline-none focus:border-ink transition-colors"
                  />
                  {errors.cvc && <p className="text-xs text-danger font-medium">{errors.cvc}</p>}
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="postalCode" className="text-xs font-bold text-muted uppercase tracking-wider">
                    ZIP Code
                  </label>
                  <input
                    id="postalCode"
                    type="text"
                    inputMode="numeric"
                    maxLength={10}
                    value={postalCode}
                    onChange={(e) => {
                      setPostalCode(e.target.value);
                      if (errors.postalCode) setErrors((prev) => ({ ...prev, postalCode: '' }));
                    }}
                    placeholder="12345"
                    className="w-full px-3 py-2.5 text-center rounded-control border border-line bg-canvas text-sm text-ink focus:outline-none focus:border-ink transition-colors"
                  />
                  {errors.postalCode && <p className="text-xs text-danger font-medium">{errors.postalCode}</p>}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5 p-3.5 rounded-card bg-surface-muted border border-line text-xs text-muted font-medium">
              <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>Sandbox payment mode active · Safe test transaction with zero charge.</span>
            </div>

            <button
              type="submit"
              disabled={isProcessing}
              className="w-full py-3.5 rounded-control bg-ink hover:opacity-90 text-white font-bold text-sm tracking-wide transition-all shadow-sm flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {isProcessing ? (
                <span>Verifying &amp; charging…</span>
              ) : (
                <>
                  <span>Pay ${reservation.totalPrice.toFixed(2)} &amp; Confirm Booking</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Right Column: Sticky Summary & Price Breakdown (5 Cols) */}
        <aside className="lg:col-span-5 bg-surface border border-line rounded-card p-6 space-y-6 sticky top-6 shadow-sm">
          {reservation.imageUrl ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={reservation.imageUrl}
              alt={reservation.hotelName}
              className="h-44 w-full rounded-card border border-line object-cover"
            />
          ) : (
            <div className="h-44 w-full rounded-card border border-line bg-surface-muted flex flex-col items-center justify-center text-muted gap-2">
              <ImageOff className="w-6 h-6 stroke-1" />
              <span className="text-xs font-medium">Photo preview unavailable</span>
            </div>
          )}

          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-muted">
              <Sparkles className="w-3.5 h-3.5 text-amber-500" />
              <span>Boutique Stay</span>
            </div>
            <h2 className="text-lg font-bold text-ink">{reservation.hotelName}</h2>
            <p className="text-xs text-muted capitalize">{reservation.roomTitle}</p>
          </div>

          <div className="grid grid-cols-2 gap-3 p-3 rounded-control bg-canvas border border-line text-xs">
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider">Check-in</span>
              <span className="font-semibold text-ink">{reservation.checkIn}</span>
            </div>
            <div>
              <span className="text-muted block text-[10px] uppercase font-bold tracking-wider">Check-out</span>
              <span className="font-semibold text-ink">{reservation.checkOut}</span>
            </div>
          </div>

          <div className="pt-2">
            <PriceBreakdown
              nightlyRate={reservation.nightlyRate}
              nights={reservation.nights}
              total={reservation.totalPrice}
            />
          </div>

          <div className="pt-2 border-t border-line">
            <CancellationPolicy checkIn={reservation.checkIn} total={reservation.totalPrice} />
          </div>
        </aside>
      </div>
    </main>
  );
}

function CheckoutRouter() {
  const searchParams = useSearchParams();
  const reservationId = searchParams.get('reservationId') || '';

  if (!reservationId) {
    return (
      <main className="max-w-xl mx-auto px-4 py-16 text-center space-y-4">
        <p role="alert" className="rounded-control bg-danger-soft border border-danger/20 p-4 text-sm text-danger">
          Missing reservation ID. Please select a room first.
        </p>
        <Link
          href="/hotels"
          className="inline-flex items-center gap-2 bg-ink text-white font-bold text-sm px-5 py-2.5 rounded-control"
        >
          Browse hotels
        </Link>
      </main>
    );
  }

  return <CheckoutContent key={reservationId} reservationId={reservationId} />;
}

export default function CheckoutPage() {
  return (
    <RequireAuth>
      <Suspense fallback={<div className="p-12 text-center text-muted">Loading checkout…</div>}>
        <CheckoutRouter />
      </Suspense>
    </RequireAuth>
  );
}