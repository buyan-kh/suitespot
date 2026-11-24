"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { CalendarCheck, LogOut, User } from "lucide-react";
import { clearTokens, getAccessToken, getRefreshToken } from "@/lib/auth";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

const subscribeAuth = (cb: () => void) => {
  window.addEventListener("suitespot-auth-change", cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener("suitespot-auth-change", cb);
    window.removeEventListener("storage", cb);
  };
};

const getIsLoggedIn = () => !!(getAccessToken() || getRefreshToken());

export default function Navbar() {
  const router = useRouter();
  const isLoggedIn = useSyncExternalStore(subscribeAuth, getIsLoggedIn, () => false);
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      const token = getAccessToken();
      await fetch(`${API_URL}/auth/logout`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).catch(() => {});
    } finally {
      clearTokens();
      window.dispatchEvent(new Event("suitespot-auth-change"));
      setLoggingOut(false);
      router.push("/");
    }
  }

  return (
    <header className="w-full bg-ink text-white py-3 sm:py-4 px-4 sm:px-6 lg:px-16 flex items-center justify-between gap-3">
      {/* Logo & Brand */}
      <Link href="/" className="flex items-center gap-2 sm:gap-3 shrink-0">
        <div className="relative w-9 h-10 shrink-0">
          <Image
            src="/logo.png"
            alt="SuiteSpot Logo Icon"
            fill
            className="object-contain"
            priority
          />
        </div>
        <div className="flex flex-col">
          <span className="font-black text-base sm:text-lg tracking-tight leading-none">
            LikeHome
          </span>
          <span className="text-[9px] sm:text-[10px] text-muted tracking-widest uppercase">
            BY SUITESPOT
          </span>
        </div>
      </Link>

      {/* Navigation Actions */}
      <div className="flex items-center gap-2 sm:gap-5">
        {isLoggedIn ? (
          <>
            <Link
              href="/bookings"
              className="text-xs font-bold hover:text-accent transition-colors h-11 px-2 sm:h-auto sm:px-0 justify-center flex items-center gap-1.5 text-white/90"
              title="My Bookings"
              aria-label="My Bookings"
            >
              <CalendarCheck aria-hidden="true" className="w-5 h-5 sm:hidden" />
              <span className="hidden sm:inline">My Bookings</span>
            </Link>

            <button
              type="button"
              onClick={handleLogout}
              disabled={loggingOut}
              className="text-xs font-bold hover:text-accent transition-colors h-11 px-2 sm:h-auto sm:px-0 justify-center flex items-center gap-1.5 text-white/90 disabled:opacity-50 cursor-pointer"
              title="Log out"
              aria-label="Log out"
            >
              <LogOut aria-hidden="true" className="w-5 h-5 sm:hidden" />
              <span className="hidden sm:inline">
                {loggingOut ? "Logging out..." : "Log out"}
              </span>
            </button>
          </>
        ) : (
          <Link
            href="/login"
            className="text-xs font-bold hover:text-accent transition-colors h-11 w-11 sm:h-auto sm:w-auto justify-center flex items-center gap-1 text-white/90"
            title="Sign in"
            aria-label="Sign in"
          >
            <User aria-hidden="true" className="w-5 h-5 sm:hidden" />
            <span className="hidden sm:inline">Sign in</span>
          </Link>
        )}

        {/* Find your stay button */}
        <Link
          href="/hotels"
          className="bg-accent hover:bg-accent-hover text-white text-xs font-bold px-3 sm:px-4 py-2.5 rounded-control flex items-center gap-1.5 whitespace-nowrap transition-all"
        >
          <span>Find your stay</span>
          <span aria-hidden="true" className="text-sm">↗</span>
        </Link>
      </div>
    </header>
  );
}