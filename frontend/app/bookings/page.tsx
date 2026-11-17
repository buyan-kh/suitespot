"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { CheckCircle2, X } from "lucide-react";
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
// Task 4.3.2 - after a cancel or change, show a confirmation here and highlight the booking.
// Other flows (e.g. the change flow, 4.3.1) can send the user back with:
//   /bookings?done=changed&id=<reservationId>    or    /bookings?done=cancelled&id=<reservationId>

type Tab = "upcoming" | "past" | "cancelled";
type Data = Record<Tab, BookingCardData[]>;

const TABS: { id: Tab; label: string; empty: string }[] = [
  { id: "upcoming", label: "Upcoming", empty: "No upcoming stays. Time to plan a trip?" },
  { id: "past", label: "Past", empty: "No past stays yet." },
  { id: "cancelled", label: "Cancelled", empty: "No cancelled bookings." },
];

const isTab = (v: string | null): v is Tab => v === "upcoming" || v === "past" || v === "cancelled";

type Done = { action: "cancelled" | "changed"; id: string; hotelName?: string };

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
  const [localDone, setLocalDone] = useState<Done | null>(null);

  const doneParam = params.get("done");
  const doneId = params.get("id");
  const fromUrl: Done | null =
    (doneParam === "cancelled" || doneParam === "changed") && doneId ? { action: doneParam, id: doneId } : null;
  const done = localDone ?? fromUrl;
  const doneBooking = done && data ? [...data.upcoming, ...data.past, ...data.cancelled].find((b) => b.id === done.id) : undefined;
  const doneName = done?.hotelName ?? doneBooking?.hotel.name;

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

  function setQuery(change: (q: URLSearchParams) => void) {
    const q = new URLSearchParams(params.toString());
    change(q);
    const query = q.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function selectTab(next: Tab) {
    setQuery((q) => {
      if (next === "upcoming") q.delete("tab");
      else q.set("tab", next);
    });
  }

  function dismissDone() {
    setLocalDone(null);
    setQuery((q) => {
      q.delete("done");
      q.delete("id");
    });
  }

  // Bring the changed/cancelled booking into view once the list has loaded.
  const doneTargetId = done?.id;
  useEffect(() => {
    if (!doneTargetId || !data) return;
    const target = document.getElementById(`booking-${doneTargetId}`) ?? document.getElementById("booking-done");
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [doneTargetId, data, tab]);

  const doneTab: Tab | null = doneBooking
    ? data!.cancelled.includes(doneBooking)
      ? "cancelled"
      : data!.past.includes(doneBooking)
        ? "past"
        : "upcoming"
    : null;

  const list = data?.[tab] ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-10 sm:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-ink">My Bookings</h1>
        <p className="mt-1 text-sm text-muted">Your stays, all in one place.</p>
      </div>

      {done && (
        <div
          id="booking-done"
          role="status"
          className="flex scroll-mt-6 items-start gap-3 rounded-card border border-success/30 bg-success-soft px-4 py-3"
        >
          <CheckCircle2 aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-success" />
          <div className="flex-1 text-sm text-ink">
            <p className="font-semibold">
              {done.action === "cancelled" ? "Booking cancelled" : "Booking updated"}
            </p>
            <p className="text-muted">
              {doneName ? `Your stay at ${doneName} ` : "Your stay "}
              {done.action === "cancelled" ? "is cancelled." : "has been updated."}
              {doneTab && doneTab !== tab && (
                <>
                  {" "}
                  <button
                    type="button"
                    onClick={() => selectTab(doneTab)}
                    className="font-semibold text-ink underline underline-offset-4 cursor-pointer"
                  >
                    View it in {TABS.find((t) => t.id === doneTab)?.label}
                  </button>
                </>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={dismissDone}
            aria-label="Dismiss"
            className="rounded-control p-1 text-muted hover:bg-surface hover:text-ink cursor-pointer"
          >
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
      )}

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
          list.map((b) => (
            <BookingCard key={b.id} booking={b} onCancel={setCancelling} highlighted={done?.id === b.id} />
          ))
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
        onCancelled={(r) => {
          setLocalDone({ action: "cancelled", id: r.id, hotelName: cancelling?.hotel.name });
          reload();
        }}
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