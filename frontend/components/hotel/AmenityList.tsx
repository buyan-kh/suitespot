"use client";

import { useEffect, useState } from "react";
import {
  Check,
  CircleParking,
  Coffee,
  Sparkles,
  Umbrella,
  UtensilsCrossed,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

// Task 1.6.2 - "What this hotel offers" list for the hotel page.
// Data: GET /hotels/{id}/amenities -> {"amenities": [{"slug", "name"}]} (task 1.6.1, Darren).
// A hotel with no amenities gets [] and shows a short note instead.
//
// Usage on the hotel page:  <AmenityList hotelId={id} />
// Or, if the hotel data already includes amenities:  <AmenityGrid amenities={hotel.amenities} />

export type Amenity = { slug: string; name: string };

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

// Slugs come from backend/app/seed/fixtures/amenities.json. Unknown ones get a check mark.
const ICONS: Record<string, LucideIcon> = {
  pool: Waves,
  "breakfast-included": Coffee,
  "spa-wellness": Sparkles,
  "beach-nearby": Umbrella,
  "free-parking": CircleParking,
  restaurant: UtensilsCrossed,
};

type State =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; amenities: Amenity[] };

export default function AmenityList({ hotelId, className }: { hotelId: string; className?: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    const abort = new AbortController();
    fetch(`${API}/hotels/${encodeURIComponent(hotelId)}/amenities`, { signal: abort.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as { amenities?: Amenity[] };
        setState({ status: "ready", amenities: Array.isArray(data.amenities) ? data.amenities : [] });
      })
      .catch((err: unknown) => {
        if ((err as Error)?.name !== "AbortError") setState({ status: "error" });
      });
    return () => abort.abort();
  }, [hotelId]);

  return (
    <section aria-labelledby="amenities-title" className={cn("space-y-4", className)}>
      <h2 id="amenities-title" className="text-xl font-bold text-ink">
        What this hotel offers
      </h2>

      {state.status === "loading" && (
        <ul className="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2 sm:grid-cols-3" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-12 animate-pulse rounded-control bg-surface-muted" />
          ))}
        </ul>
      )}

      {state.status === "error" && (
        <p className="text-sm text-muted">Couldn&apos;t load amenities right now.</p>
      )}

      {state.status === "ready" && <AmenityGrid amenities={state.amenities} />}
    </section>
  );
}

export function AmenityGrid({ amenities }: { amenities: Amenity[] }) {
  if (amenities.length === 0) {
    return <p className="text-sm text-muted">This hotel hasn&apos;t listed any amenities yet.</p>;
  }

  return (
    <ul className="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2 sm:grid-cols-3">
      {amenities.map((a) => {
        const Icon = ICONS[a.slug] ?? Check;
        return (
          <li
            key={a.slug}
            className="flex items-center gap-3 rounded-control border border-line bg-surface px-3.5 py-3"
          >
            <Icon aria-hidden="true" className="h-5 w-5 shrink-0 text-ink" />
            <span className="text-sm font-medium text-ink">{a.name}</span>
          </li>
        );
      })}
    </ul>
  );
}