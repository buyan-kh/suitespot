"use client";

import { useState } from "react";
import RequireAuth from "@/components/auth/RequireAuth";
import CancelDialog, { type CancelledReservation } from "@/components/booking/CancelDialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

// Temporary page to test the cancel flow (2.2.2 / 2.2.3) until My Bookings (4.1.2) exists.
// Flow: hold a room on /hotels/[id], copy the Reference id, paste it here, cancel.
export default function TestCancelPage() {
  const [id, setId] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<CancelledReservation | null>(null);

  return (
    <RequireAuth>
      <div className="mx-auto max-w-md space-y-6 px-4 py-12">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Test: cancel a reservation</h1>
          <p className="mt-1 text-sm text-muted">
            Hold a room on a hotel page, copy the Reference id, and paste it here.
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="reservation-id" className="block text-sm font-medium text-ink">
            Reservation id
          </label>
          <Input
            id="reservation-id"
            value={id}
            onChange={(e) => {
              setId(e.target.value.trim());
              setResult(null);
            }}
            placeholder="e.g. 3f2a…"
          />
        </div>

        <Button variant="destructive" disabled={!id} onClick={() => setOpen(true)}>
          Cancel reservation
        </Button>

        {result && (
          <p role="status" className="rounded-control bg-success-soft px-3 py-2 text-sm text-ink">
            Status is now <strong>{result.status}</strong> ({result.check_in_date} to {result.check_out_date})
          </p>
        )}

        <CancelDialog
          open={open}
          reservation={{ id }}
          onClose={() => setOpen(false)}
          onCancelled={setResult}
        />
      </div>
    </RequireAuth>
  );
}