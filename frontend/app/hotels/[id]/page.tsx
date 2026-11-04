"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { authFetch, getAccessToken, getRefreshToken } from "@/lib/auth";
import { Star, MapPin, ArrowRight } from "lucide-react";

type Room = {
  id: string;
  room_number: string;
  room_type: string;
  price_per_night: number;
  max_guests: number;
  available: boolean;
};

type Hotel = {
  id: string;
  name: string;
  description?: string;
  address: string;
  city: string;
  country: string;
  star_rating: number;
  image_url?: string;
  rooms: Room[];
};

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

function Details() {
  const route = useParams();
  const params = useSearchParams();
  const router = useRouter();
  const id = String(route.id);

  const [hotel, setHotel] = useState<Hotel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);

  const [checkIn, setCheckIn] = useState(params.get("checkIn") || "");
  const [checkOut, setCheckOut] = useState(params.get("checkOut") || "");
  const guests = Math.max(1, Number(params.get("adults") || 1) + Number(params.get("children") || 0));

  useEffect(() => {
    const abort = new AbortController();

    async function fetchHotel() {
      setLoading(true);
      setError("");

      try {
        const query = new URLSearchParams({ guests: String(guests) });
        if (checkIn && checkOut) {
          query.set("checkIn", checkIn);
          query.set("checkOut", checkOut);
        }

        const res = await fetch(`${API}/hotels/${encodeURIComponent(id)}?${query}`, {
          signal: abort.signal,
        });

        if (!res.ok) throw new Error(`Hotel lookup failed (HTTP ${res.status})`);
        const data = (await res.json()) as Hotel;
        if (abort.signal.aborted) return;
        setHotel(data);
        setSelected((old) =>
          data.rooms.some((r) => r.id === old && r.available)
            ? old
            : data.rooms.find((r) => r.available)?.id || ""
        );
      } catch (err) {
        if (!abort.signal.aborted) {
          setError(err instanceof Error ? err.message : "Failed to load stay");
        }
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    }

    fetchHotel();
    return () => abort.abort();
  }, [id, guests, checkIn, checkOut]);

  async function reserve() {
    if (!selected || !checkIn || !checkOut || checkOut <= checkIn) {
      setError("Select an available room and valid dates.");
      return;
    }

    if (!getAccessToken() && !getRefreshToken()) {
      router.push(`/login?next=${encodeURIComponent(`/hotels/${id}?${params.toString()}`)}`);
      return;
    }

    setBusy(true);
    setError("");

    try {
      const r = await authFetch("/reservations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          room_id: selected,
          check_in: checkIn,
          check_out: checkOut,
          num_guests: guests,
        }),
      });

      if (r.status === 401) {
        router.push(`/login?next=${encodeURIComponent(`/hotels/${id}?${params.toString()}`)}`);
        return;
      }

      if (!r.ok) {
        const info = await r.json().catch(() => ({}));
        throw new Error(
          typeof info.detail === "string" ? info.detail : `Booking failed (HTTP ${r.status})`
        );
      }

      const confirmation = await r.json();

      // Immediately navigate to checkout with the active reservation hold ID
      router.push(`/checkout?reservationId=${confirmation.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Booking failed.");
      setBusy(false);
    }
  }

  return (
    <main className="max-w-5xl mx-auto px-4 sm:px-8 py-10 space-y-6 min-h-screen text-ink">
      <Link
        href={`/hotels?${params.toString()}`}
        className="text-xs font-bold text-muted hover:text-ink transition-colors"
      >
        ← Back to stays
      </Link>

      {loading ? (
        <div className="p-12 text-center text-muted">Loading room details…</div>
      ) : error && !hotel ? (
        <div className="p-6 rounded-card border border-danger/30 bg-danger-soft text-danger text-sm font-medium">
          {error}
        </div>
      ) : hotel ? (
        <div className="space-y-8">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="flex items-center gap-1 text-xs font-bold bg-white px-2.5 py-1 rounded-control border border-line">
                <Star className="w-3.5 h-3.5 fill-ink text-ink" /> {hotel.star_rating} Stars
              </span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-black tracking-tight">{hotel.name}</h1>
            <p className="flex items-center gap-1.5 text-sm text-muted font-medium mt-1">
              <MapPin className="w-4 h-4 text-ink" /> {hotel.address}, {hotel.city}, {hotel.country}
            </p>
          </div>

          {hotel.image_url && (
            <div className="aspect-[16/9] max-h-96 w-full rounded-card overflow-hidden shadow-sm">
              <img src={hotel.image_url} alt={hotel.name} className="w-full h-full object-cover" />
            </div>
          )}

          {hotel.description && (
            <p className="text-muted text-base leading-relaxed">{hotel.description}</p>
          )}

          {/* Stay Dates */}
          <div className="grid sm:grid-cols-2 gap-4 p-4 rounded-card border border-line bg-surface">
            <div>
              <label className="block text-[10px] font-bold text-muted uppercase tracking-wider mb-1">
                Check-in
              </label>
              <input
                className="w-full bg-transparent font-bold text-sm text-ink focus:outline-none cursor-pointer"
                type="date"
                value={checkIn}
                onChange={(e) => setCheckIn(e.target.value)}
              />
            </div>
            <div className="sm:border-l sm:border-line sm:pl-4">
              <label className="block text-[10px] font-bold text-muted uppercase tracking-wider mb-1">
                Check-out
              </label>
              <input
                className="w-full bg-transparent font-bold text-sm text-ink focus:outline-none cursor-pointer"
                type="date"
                min={checkIn}
                value={checkOut}
                onChange={(e) => setCheckOut(e.target.value)}
              />
            </div>
          </div>

          {/* Room Selection */}
          <div className="space-y-4">
            <h2 className="text-xl font-black tracking-tight">
              Select Room ({guests} guest{guests === 1 ? "" : "s"})
            </h2>

            <div className="space-y-3">
              {hotel.rooms.map((room) => {
                const isSelected = room.id === selected;
                return (
                  <label
                    key={room.id}
                    onClick={() => room.available && setSelected(room.id)}
                    className={`flex items-center justify-between p-4 rounded-card border transition-all ${
                      !room.available
                        ? "opacity-40 cursor-not-allowed border-line bg-surface/40"
                        : isSelected
                        ? "border-ink bg-surface shadow-md cursor-pointer"
                        : "border-line bg-surface hover:border-line-strong cursor-pointer"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="radio"
                        name="room"
                        disabled={!room.available}
                        checked={isSelected}
                        onChange={() => setSelected(room.id)}
                        className="w-4 h-4 accent-ink cursor-pointer"
                      />
                      <div>
                        <p className="font-bold text-base capitalize">{room.room_type} Room</p>
                        <p className="text-xs text-muted">
                          Room #{room.room_number} · Max {room.max_guests} guests
                        </p>
                      </div>
                    </div>

                    <div className="text-right">
                      <p className="text-lg font-black">
                        ${room.price_per_night}
                        <span className="text-xs font-normal text-muted"> / night</span>
                      </p>
                      <span
                        className={`text-[10px] font-bold uppercase ${
                          room.available ? "text-success" : "text-danger"
                        }`}
                      >
                        {room.available ? "Available" : "Unavailable"}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {error && (
            <div className="p-3 text-sm text-danger bg-danger-soft border border-danger/20 rounded-control">
              {error}
            </div>
          )}

          {/* Action Trigger */}
          <div className="pt-4 border-t border-line space-y-3">
            <button
              onClick={reserve}
              disabled={busy || !selected}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white px-8 py-4 rounded-control font-bold text-sm transition-all shadow-sm disabled:opacity-50 cursor-pointer"
            >
              <span>{busy ? "Securing hold…" : "Proceed to Checkout"}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <p className="text-xs text-muted">
              Creates an instant 15-minute hold on your room before payment is finalized[cite: 1].
            </p>
          </div>
        </div>
      ) : null}
    </main>
  );
}

export default function HotelDetailPage() {
  return (
    <Suspense fallback={<p className="p-8 text-center text-muted">Loading stay…</p>}>
      <Details />
    </Suspense>
  );
}