"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import RequireAuth from "@/components/auth/RequireAuth";
import BookingCard, { type BookingCardData } from "@/components/bookings/BookingCard";
import CancelDialog from "@/components/booking/CancelDialog";
import { Button } from "@/components/ui/Button";
import { authFetch } from "@/lib/auth";
import { cn } from "@/lib/utils";

// Task 4.1.2 - My Bookings page with Upcoming / Past / Cancelled tabs.
// Data: GET /me/reservations (4.1.1). The open tab is kept in the URL (?tab=past).

type Tab = "upcoming" | "past" | "cancelled";
type Data = Record<Tab, BookingCardData[]>;

const TABS: { id: Tab; label: string; empty: string }[] = [
  { id: "upcoming", label: "Upcoming", empty: "No upcoming stays. Time to plan a trip?" },
  { id: "past", label: "Past", empty: "No past stays yet." },
  { id: "cancelled", label: "Cancelled", empty: "No cancelled bookings." },
];

const isTab = (v: string | null): v is Tab => v === "upcoming" || v === "past" || v === "cancelled";

async function fetchBookings(): Promise<Data> {
  const res = await authFetch("/me/reservations");
  if (!res.ok) throw new Error(String(res.status));
  const body = await res.json();
  return { upcoming: body.upcoming ?? [], past: body.past ?? [], cancelled: body.cancelled ?? [] };
}

function MyBookings() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tabParam = params.get("tab");
  const tab: Tab = isTab(tabParam) ? tabParam : "upcoming";

  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState<BookingCardData | null>(null);

  const reload = useCallback(() => {
    fetchBookings()
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch(() => setError("Couldn't load your bookings. Please try again."));
  }, []);

  useEffect(() => {
    let active = true;
    fetchBookings()
      .then((d) => active && setData(d))
      .catch(() => active && setError("Couldn't load your bookings. Please try again."));
    return () => {
      active = false;
    };
  }, []);

  function selectTab(next: Tab) {
    const q = new URLSearchParams(params.toString());
    if (next === "upcoming") q.delete("tab");
    else q.set("tab", next);
    const query = q.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const list = data?.[tab] ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-10 sm:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-ink">My Bookings</h1>
        <p className="mt-1 text-sm text-muted">Your stays, all in one place.</p>
      </div>

      <div role="tablist" aria-label="Booking groups" className="flex gap-1 border-b border-line">
        {TABS.map((t) => {
          const selected = t.id === tab;
          const count = data?.[t.id].length;
          return (
            <button
              key={t.id}
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={selected}
              aria-controls="booking-panel"
              onClick={() => selectTab(t.id)}
              className={cn(
                "-mb-px border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
                selected ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
              )}
            >
              {t.label}
              {count !== undefined && <span className="ml-1.5 text-xs text-muted">({count})</span>}
            </button>
          );
        })}
      </div>

      <section id="booking-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="space-y-4">
        {error ? (
          <div className="space-y-3 rounded-card border border-line bg-surface p-6 text-center">
            <p role="alert" className="text-sm text-danger">{error}</p>
            <Button variant="outline" onClick={reload}>Try again</Button>
          </div>
        ) : !data ? (
          [0, 1].map((i) => <div key={i} className="h-44 animate-pulse rounded-card bg-surface-muted" aria-hidden="true" />)
        ) : list.length === 0 ? (
          <div className="space-y-3 rounded-card border border-dashed border-line-strong bg-surface p-10 text-center">
            <p className="text-sm text-muted">{TABS.find((t) => t.id === tab)?.empty}</p>
            {tab === "upcoming" && (
              <Link
                href="/hotels"
                className="inline-flex h-10 items-center rounded-control bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover"
              >
                Find a stay
              </Link>
            )}
          </div>
        ) : (
          list.map((b) => <BookingCard key={b.id} booking={b} onCancel={setCancelling} />)
        )}
      </section>

      <CancelDialog
        open={!!cancelling}
        reservation={{
          id: cancelling?.id ?? "",
          hotelName: cancelling?.hotel.name,
          checkIn: cancelling?.check_in,
          checkOut: cancelling?.check_out,
        }}
        onClose={() => setCancelling(null)}
        onCancelled={reload}
      />
    </div>
  );
}

export default function MyBookingsPage() {
  return (
    <RequireAuth>
      <Suspense>
        <MyBookings />
      </Suspense>
    </RequireAuth>
  );
}