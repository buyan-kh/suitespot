"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { authFetch } from "@/lib/auth";

// Task 2.2.2 - "are you sure?" dialog for cancelling a reservation.
// Backend: POST /reservations/{id}/cancel (task 2.2.1, David).
//   200 -> cancelled (also when it was already cancelled), 404 -> not found / not yours,
//   409 -> can't be cancelled (stay started, etc.), 401 -> not logged in.
// Cancellation fees by tier are 3.3.2/3.3.3, so this dialog doesn't show amounts yet.
//
// Usage:
//   <CancelDialog open={open} reservation={{ id, hotelName, checkIn, checkOut }}
//     onClose={() => setOpen(false)} onCancelled={(r) => refreshList()} />

export type CancelledReservation = {
  id: string;
  status: string;
  check_in_date: string;
  check_out_date: string;
  total_price: number;
};

type ReservationSummary = {
  id: string;
  hotelName?: string;
  checkIn?: string; // YYYY-MM-DD
  checkOut?: string; // YYYY-MM-DD
};

type CancelDialogProps = {
  open: boolean;
  reservation: ReservationSummary;
  onClose: () => void;
  onCancelled?: (reservation: CancelledReservation) => void;
};

type Step = "confirm" | "submitting" | "done";

function errorMessage(status: number, body: unknown): string {
  if (status === 401) return "Your session expired. Please log in again and retry.";
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg;
  if (typeof detail === "string") return detail;
  if (status === 404) return "We couldn't find this reservation.";
  if (status === 409) return "This reservation can no longer be cancelled.";
  return "Couldn't cancel right now. Please try again.";
}

function formatDate(value?: string) {
  if (!value) return "";
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function CancelDialog({ open, reservation, onClose, onCancelled }: CancelDialogProps) {
  if (!open) return null;
  // Fresh state every time it opens.
  return <DialogBody reservation={reservation} onClose={onClose} onCancelled={onCancelled} />;
}

function DialogBody({ reservation, onClose, onCancelled }: Omit<CancelDialogProps, "open">) {
  const [step, setStep] = useState<Step>("confirm");
  const [error, setError] = useState("");
  const keepRef = useRef<HTMLButtonElement>(null);
  const doneRef = useRef<HTMLButtonElement>(null);
  const busy = step === "submitting";

  // Focus the safe choice, lock page scroll, restore focus on close.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    keepRef.current?.focus();
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      previouslyFocused?.focus();
    };
  }, []);

  useEffect(() => {
    if (step === "done") doneRef.current?.focus();
  }, [step]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function confirmCancel() {
    setStep("submitting");
    setError("");
    try {
      const res = await authFetch(`/reservations/${encodeURIComponent(reservation.id)}/cancel`, {
        method: "POST",
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setError(errorMessage(res.status, body));
        setStep("confirm");
        return;
      }
      setStep("done");
      onCancelled?.(body as CancelledReservation);
    } catch {
      setError("Can't reach the server right now. Please try again.");
      setStep("confirm");
    }
  }

  const dates =
    reservation.checkIn && reservation.checkOut
      ? `${formatDate(reservation.checkIn)} – ${formatDate(reservation.checkOut)}`
      : "";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-black/50 p-4 sm:items-center"
      onClick={() => !busy && onClose()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="cancel-title"
        aria-describedby="cancel-desc"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md rounded-card border border-line bg-surface p-6 shadow-lg"
      >
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label="Close"
          className="absolute right-3 top-3 rounded-control p-1.5 text-muted hover:bg-surface-muted hover:text-ink disabled:opacity-50 cursor-pointer"
        >
          <X aria-hidden="true" className="h-5 w-5" />
        </button>

        {step === "done" ? (
          <div className="space-y-4 text-center">
            <CheckCircle2 aria-hidden="true" className="mx-auto h-10 w-10 text-success" />
            <h2 id="cancel-title" className="text-lg font-semibold text-ink">
              Reservation cancelled
            </h2>
            <p id="cancel-desc" className="text-sm text-muted" role="status">
              {reservation.hotelName ? `Your stay at ${reservation.hotelName} is cancelled.` : "Your stay is cancelled."}{" "}
              The room is released for other guests.
            </p>
            <Button ref={doneRef} className="w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-danger-soft">
              <AlertTriangle aria-hidden="true" className="h-5 w-5 text-danger" />
            </div>
            <div className="space-y-1">
              <h2 id="cancel-title" className="text-lg font-semibold text-ink">
                Cancel this reservation?
              </h2>
              <p id="cancel-desc" className="text-sm text-muted">
                {(reservation.hotelName || dates) && (
                  <>
                    <span className="font-medium text-ink">{reservation.hotelName ?? "Your stay"}</span>
                    {dates && <> · {dates}</>}
                    <br />
                  </>
                )}
                This can&apos;t be undone. Cancellation fees follow the hotel&apos;s cancellation policy.
              </p>
            </div>

            {error && (
              <p role="alert" className="rounded-control bg-danger-soft px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}

            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button ref={keepRef} variant="outline" onClick={onClose} disabled={busy}>
                Keep reservation
              </Button>
              <Button variant="destructive" onClick={confirmCancel} disabled={busy}>
                {busy ? "Cancelling..." : "Yes, cancel"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}