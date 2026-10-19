"use client";
import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { authFetch, getAccessToken, getRefreshToken } from "@/lib/auth";

type Room = { id: string; room_number: string; room_type: string; price_per_night: number; max_guests: number; available: boolean };
type Hotel = { id: string; name: string; description?: string; address: string; city: string; country: string; star_rating: number; image_url?: string; rooms: Room[] };
const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
function Details() {
  const route = useParams(); const params = useSearchParams(); const router = useRouter();
  const id = String(route.id); const [hotel, setHotel] = useState<Hotel | null>(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const [selected, setSelected] = useState(""); const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");
  const [checkIn, setCheckIn] = useState(params.get("checkIn") || "");
  const [checkOut, setCheckOut] = useState(params.get("checkOut") || "");
  const guests = Math.max(1, Number(params.get("adults") || 1) + Number(params.get("children") || 0));
  useEffect(() => {
    const abort = new AbortController();
    const query = new URLSearchParams({guests: String(guests)});
    if (checkIn && checkOut) {query.set("checkIn", checkIn); query.set("checkOut", checkOut);}
    fetch(`${API}/hotels/${encodeURIComponent(id)}?${query}`, {signal: abort.signal})
      .then(async r => {if (!r.ok) throw new Error(`Hotel lookup failed (HTTP ${r.status})`); return r.json();})
      .then((data: Hotel) => {setHotel(data); setSelected(old => data.rooms.some(r => r.id === old && r.available) ? old : data.rooms.find(r => r.available)?.id || "");})
      .catch(e => {if (!abort.signal.aborted) setError(String(e));})
      .finally(() => {if (!abort.signal.aborted) setLoading(false);});
    return () => abort.abort();
  }, [id, guests, checkIn, checkOut]);
  async function reserve() {
    if (!selected || !checkIn || !checkOut || checkOut <= checkIn) {setError("Select an available room and valid dates."); return;}
    if (!getAccessToken() && !getRefreshToken()) {
      router.push(`/login?next=${encodeURIComponent(`/hotels/${id}?${params.toString()}`)}`); return;
    }
    setBusy(true); setError(""); setSuccess("");
    try {
      const r = await authFetch("/reservations", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({room_id: selected, check_in: checkIn, check_out: checkOut, num_guests: guests})});
      if (r.status === 401) {router.push(`/login?next=${encodeURIComponent(`/hotels/${id}?${params.toString()}`)}`); return;}
      if (!r.ok) {const info = await r.json().catch(() => ({})); throw new Error(typeof info.detail === "string" ? info.detail : `Booking failed (HTTP ${r.status})`);}
      const confirmation = await r.json();
      setSuccess(`Room hold created! Reference: ${confirmation.id}. Status: ${confirmation.status}. This hold expires in approximately 15 minutes if not finalized.`);
    } catch (e) {setError(e instanceof Error ? e.message : "Booking failed.");} finally {setBusy(false);}
  }
  return <main className="max-w-5xl mx-auto px-4 sm:px-8 py-10 space-y-6 min-h-screen">
    <Link href={`/hotels?${params.toString()}`} className="underline">← Back to hotels</Link>
    {loading ? <p>Loading rooms…</p> : error && !hotel ? <p role="alert" className="text-red-600">{error}</p> : hotel ? <>
      <h1 className="text-3xl font-black">{hotel.name}</h1>
      <p>{hotel.address}, {hotel.city}, {hotel.country} · {hotel.star_rating} stars</p>
      {hotel.image_url && <img src={hotel.image_url} alt={hotel.name} className="w-full max-h-96 object-cover rounded-lg" />}
      {hotel.description && <p>{hotel.description}</p>}
      <div className="grid sm:grid-cols-2 gap-4"><label>Check-in <input className="block border p-3 w-full" type="date" value={checkIn} onChange={e => setCheckIn(e.target.value)} /></label>
        <label>Check-out <input className="block border p-3 w-full" type="date" value={checkOut} onChange={e => setCheckOut(e.target.value)} /></label></div>
      <h2 className="text-xl font-bold">Room availability ({guests} guest{guests === 1 ? "" : "s"})</h2>
      <div className="space-y-3">{hotel.rooms.map(room => <label key={room.id} className={`block border rounded-lg p-4 ${room.available ? "cursor-pointer" : "opacity-50"}`}>
        <input type="radio" name="room" disabled={!room.available} checked={room.id === selected} onChange={() => setSelected(room.id)} />
        <span className="ml-3 font-semibold">{room.room_type} · Room {room.room_number}</span>
        <span className="ml-3">${room.price_per_night}/night · Up to {room.max_guests} guests</span>
        <span className="ml-3">{room.available ? "Available" : "Unavailable"}</span>
      </label>)}</div>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      {success && <p role="status" className="text-green-700">{success}</p>}
      <button onClick={reserve} disabled={busy || !selected || !!success} className="bg-ink text-white px-6 py-3 rounded-lg disabled:opacity-50">{busy ? "Reserving…" : "Hold this room"}</button>
      <p className="text-sm text-stone-600">No payment is taken yet. Payment and final confirmation are part of Sprint 4.</p>
    </> : null}
  </main>;
}
export default function HotelDetailPage() { return <Suspense fallback={<p>Loading…</p>}><Details /></Suspense>; }
