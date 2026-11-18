"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import SearchBar from "@/components/search/SearchBar";
import FilterPanel from "@/components/search/FilterPanel";
import SortControl from "@/components/search/SortControl";
import NoResults from "@/components/search/NoResults";
import { useScrollMemory } from "@/lib/useScrollMemory";

type HotelResult = {
  id: string;
  name: string;
  city: string;
  state?: string | null;
  star_rating: number;
  image_url?: string | null;
  rooms_available: number;
  from_price: number;
  distance_km?: number | null;
};

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

function Results() {
  const params = useSearchParams();
  const query = params.toString();
  const [results, setResults] = useState<HotelResult[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const destination = params.get("destination");
  const checkIn = params.get("checkIn");
  const checkOut = params.get("checkOut");
  const valid = !!(destination && checkIn && checkOut);

  // Task 1.7.2: Preserve scroll position across filter changes & back/forward navigation
  useScrollMemory(query, !loading);

  useEffect(() => {
    if (!valid) return;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        const q = new URLSearchParams(query);
        const adults = Number(q.get("adults") || 1);
        const children = Number(q.get("children") || 0);
        const guests = Math.max(1, adults + children);
        q.set("guests", String(guests));

        const res = await fetch(`${API}/search?${q.toString()}`, { signal: controller.signal });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          const msg = Array.isArray(body?.detail) && body.detail[0]?.msg
            ? body.detail[0].msg
            : `Search failed (HTTP ${res.status}).`;
          throw new Error(msg);
        }
        const data = await res.json();
        if (!controller.signal.aborted) {
          setResults(data.results ?? []);
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "Search failed.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [query, valid]);

  return (
    <main className="bg-canvas min-h-screen text-ink py-8 px-4 sm:px-8 lg:px-16 max-w-[1600px] mx-auto space-y-8">
      <SearchBar
        defaultValues={{
          destination: destination || "",
          checkIn: checkIn || "",
          checkOut: checkOut || "",
          adults: Number(params.get("adults")) || 2,
          children: Number(params.get("children")) || 0,
        }}
      />
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        <aside className="lg:col-span-3">
          <FilterPanel />
        </aside>
        <div className="lg:col-span-9 space-y-6">
          <div className="flex flex-wrap justify-between items-center gap-4">
            <div className="flex items-center gap-3">
              <h1 className="font-bold text-2xl">Available hotels</h1>
              {loading && results.length > 0 && (
                <span aria-live="polite" className="text-xs font-medium text-muted">
                  Updating results…
                </span>
              )}
            </div>
            <SortControl />
          </div>

          {!valid ? (
            <p className="text-sm text-muted">
              Enter a destination, check-in date, and check-out date to see available rooms.
            </p>
          ) : loading && results.length === 0 ? (
            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-6" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-80 animate-pulse rounded-card bg-surface-muted" />
              ))}
            </div>
          ) : error ? (
            <p role="alert" className="rounded-control bg-danger-soft p-4 text-sm text-danger">
              {error}
            </p>
          ) : !results.length ? (
            <NoResults
              destination={destination || undefined}
              checkIn={checkIn || undefined}
              checkOut={checkOut || undefined}
              onChangeSearch={() => document.getElementById("destination")?.focus()}
            />
          ) : (
            <div
              className={`grid sm:grid-cols-2 xl:grid-cols-3 gap-6 transition-opacity ${
                loading ? "opacity-60 pointer-events-none" : "opacity-100"
              }`}
            >
              {results.map((h) => (
                <article
                  key={h.id}
                  className="border border-line rounded-card overflow-hidden bg-surface shadow-sm flex flex-col justify-between"
                >
                  {h.image_url ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img src={h.image_url} alt={h.name} className="h-48 w-full object-cover" />
                  ) : (
                    <div className="h-48 bg-surface-muted flex items-center justify-center text-xs text-muted">
                      No photo available
                    </div>
                  )}
                  <div className="p-5 space-y-3 flex-grow flex flex-col justify-between">
                    <div>
                      <h2 className="font-bold text-xl">{h.name}</h2>
                      <p className="text-sm text-muted">
                        {h.city}
                        {h.state ? `, ${h.state}` : ""} · {h.star_rating} stars
                        {typeof h.distance_km === "number" ? ` · ${h.distance_km} km from center` : ""}
                      </p>
                      <p className="text-sm text-muted mt-1">{h.rooms_available} available room(s)</p>
                    </div>
                    <div className="pt-2">
                      <p className="font-bold text-base mb-3">
                        From ${h.from_price}
                        <span className="text-xs font-normal text-muted"> / night</span>
                      </p>
                      <Link
                        href={`/hotels/${h.id}?${query}`}
                        className="block text-center bg-ink text-white font-semibold rounded-control px-4 py-3 hover:bg-primary-hover transition-colors"
                      >
                        View rooms and book
                      </Link>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

export default function HotelsPage() {
  return (
    <Suspense fallback={<p className="p-8 text-muted">Loading…</p>}>
      <Results />
    </Suspense>
  );
}