"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { MapPin, Star } from "lucide-react";
import PhotoGallery, { type GalleryImage } from "@/components/hotel/PhotoGallery";
import AmenityList from "@/components/hotel/AmenityList";
import BookingWidget, { type SelectedRoom } from "@/components/hotel/BookingWidget";
import CancellationPolicy from "@/components/policy/CancellationPolicy";

type HotelDetail = {
  id: string;
  name: string;
  description?: string;
  address: string;
  city: string;
  state?: string;
  country: string;
  star_rating: number;
  image_url?: string;
  rooms: SelectedRoom[];
};

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

function Details() {
  const route = useParams();
  const params = useSearchParams();
  const id = String(route.id);

  const [hotel, setHotel] = useState<HotelDetail | null>(null);
  const [gallery, setGallery] = useState<GalleryImage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState("");

  const [checkIn, setCheckIn] = useState(params.get("checkIn") || "");
  const [checkOut, setCheckOut] = useState(params.get("checkOut") || "");
  const [adults, setAdults] = useState(Math.max(1, Number(params.get("adults") || 1)));
  const [childrenCount, setChildrenCount] = useState(Math.max(0, Number(params.get("children") || 0)));

  const totalGuests = adults + childrenCount;

  // Fetch gallery images once per hotel
  useEffect(() => {
    const abort = new AbortController();
    fetch(`${API}/hotels/${encodeURIComponent(id)}/images`, { signal: abort.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!abort.signal.aborted && Array.isArray(data?.images)) {
          setGallery(data.images);
        }
      })
      .catch(() => {});
    return () => abort.abort();
  }, [id]);

  // Fetch hotel details & live room availability when dates/guests change
  useEffect(() => {
    const abort = new AbortController();

    async function fetchHotel() {
      setLoading(true);
      setError("");

      try {
        const query = new URLSearchParams({ guests: String(totalGuests) });
        if (checkIn && checkOut && checkOut > checkIn) {
          query.set("checkIn", checkIn);
          query.set("checkOut", checkOut);
        }

        const res = await fetch(`${API}/hotels/${encodeURIComponent(id)}?${query}`, {
          signal: abort.signal,
        });

        if (!res.ok) {
          throw new Error(res.status === 404 ? "Hotel not found." : `Hotel lookup failed (HTTP ${res.status})`);
        }
        const data = (await res.json()) as HotelDetail;
        if (abort.signal.aborted) return;

        setHotel(data);
        setSelectedId((old) =>
          data.rooms.some((r) => r.id === old && r.available)
            ? old
            : data.rooms.find((r) => r.available)?.id || ""
        );
      } catch (err: unknown) {
        if (!abort.signal.aborted) {
          setError(err instanceof Error ? err.message : "Failed to load hotel details.");
        }
      } finally {
        if (!abort.signal.aborted) setLoading(false);
      }
    }

    fetchHotel();
    return () => abort.abort();
  }, [id, totalGuests, checkIn, checkOut]);

  const selectedRoom = hotel?.rooms.find((r) => r.id === selectedId) ?? null;
  const nights =
    checkIn && checkOut && checkOut > checkIn
      ? Math.round(
          (new Date(`${checkOut}T00:00:00`).getTime() -
            new Date(`${checkIn}T00:00:00`).getTime()) /
            (1000 * 60 * 60 * 24)
        )
      : 0;
  const estimatedTotal =
    selectedRoom && nights > 0 ? (Math.round(selectedRoom.price_per_night * 100) * nights) / 100 : undefined;

  // Fallback single-image gallery if /images has no uploaded files yet
  const effectiveGallery: GalleryImage[] =
    gallery.length > 0
      ? gallery
      : hotel?.image_url
      ? [
          {
            url: hotel.image_url,
            alt: hotel.name,
            width: 1600,
            height: 900,
            sizes: {
              thumb: hotel.image_url,
              medium: hotel.image_url,
              large: hotel.image_url,
            },
          },
        ]
      : [];

  return (
    <main className="max-w-6xl mx-auto px-4 sm:px-8 py-8 space-y-8 min-h-screen">
      <Link
        href={params.toString() ? `/hotels?${params.toString()}` : "/hotels"}
        className="inline-block text-sm font-medium text-muted hover:text-ink underline"
      >
        ← Back to hotels
      </Link>

      {loading && !hotel ? (
        <p className="text-muted">Loading hotel details…</p>
      ) : error && !hotel ? (
        <p role="alert" className="rounded-control bg-danger-soft p-4 text-sm text-danger">
          {error}
        </p>
      ) : hotel ? (
        <>
          {/* Header */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl sm:text-4xl font-black text-ink tracking-tight">{hotel.name}</h1>
              <span className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-3 py-1 text-xs font-bold text-ink">
                <Star aria-hidden="true" className="h-3.5 w-3.5 fill-ink" />
                {hotel.star_rating} stars
              </span>
            </div>
            <p className="flex items-center gap-1.5 text-sm text-muted">
              <MapPin aria-hidden="true" className="h-4 w-4 shrink-0" />
              {[hotel.address, hotel.city, hotel.state, hotel.country].filter(Boolean).join(", ")}
            </p>
          </div>

          {/* Photo Gallery */}
          <PhotoGallery images={effectiveGallery} title={hotel.name} />

          {/* Main 2-column layout */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-7 space-y-8">
              {hotel.description && (
                <section className="space-y-2">
                  <h2 className="text-xl font-bold text-ink">About this stay</h2>
                  <p className="text-sm sm:text-base text-muted leading-relaxed">{hotel.description}</p>
                </section>
              )}

              <AmenityList hotelId={hotel.id} />

              {/* Room Selection */}
              <section aria-labelledby="rooms-title" className="space-y-4">
                <div className="flex items-baseline justify-between">
                  <h2 id="rooms-title" className="text-xl font-bold text-ink">
                    Select a room
                  </h2>
                  <span className="text-xs text-muted">
                    Showing availability for {totalGuests} guest{totalGuests === 1 ? "" : "s"}
                  </span>
                </div>

                {hotel.rooms.length === 0 ? (
                  <p className="text-sm text-muted">No rooms listed for this hotel.</p>
                ) : (
                  <div className="space-y-3">
                    {hotel.rooms.map((room) => {
                      const isSelected = room.id === selectedId;
                      return (
                        <label
                          key={room.id}
                          className={`flex items-center justify-between gap-4 border rounded-card p-4 transition-all ${
                            room.available
                              ? isSelected
                                ? "border-ink bg-surface shadow-sm cursor-pointer"
                                : "border-line bg-surface hover:border-line-strong cursor-pointer"
                              : "border-line bg-surface-muted/50 opacity-60 cursor-not-allowed"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <input
                              type="radio"
                              name="room"
                              disabled={!room.available}
                              checked={isSelected}
                              onChange={() => setSelectedId(room.id)}
                              className="mt-1 accent-ink"
                            />
                            <div>
                              <p className="font-bold text-ink capitalize">
                                {room.room_type} · Room {room.room_number}
                              </p>
                              <p className="text-xs text-muted mt-0.5">
                                Up to {room.max_guests} guest{room.max_guests === 1 ? "" : "s"}
                              </p>
                            </div>
                          </div>

                          <div className="text-right shrink-0">
                            <p className="font-bold text-ink">${room.price_per_night} / night</p>
                            <span
                              className={`inline-block mt-1 text-xs font-semibold ${
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
                )}
              </section>

              <CancellationPolicy checkIn={checkIn || undefined} total={estimatedTotal} />
            </div>

            {/* Sticky Booking Sidebar */}
            <div className="lg:col-span-5">
              <BookingWidget
                room={selectedRoom}
                checkIn={checkIn}
                checkOut={checkOut}
                adults={adults}
                childrenCount={childrenCount}
                onCheckInChange={setCheckIn}
                onCheckOutChange={setCheckOut}
                onGuestsChange={(a, c) => {
                  setAdults(a);
                  setChildrenCount(c);
                }}
              />
            </div>
          </div>
        </>
      ) : null}
    </main>
  );
}

export default function HotelDetailPage() {
  return (
    <Suspense fallback={<p className="p-8 text-muted">Loading…</p>}>
      <Details />
    </Suspense>
  );
}