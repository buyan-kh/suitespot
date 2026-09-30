import Link from "next/link";
import { Button } from "@/components/ui/Button";

export function Navbar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-stone-200/80 bg-stone-50/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 h-16 flex items-center justify-between gap-1 sm:gap-4">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-1 shrink-0">
          <span className="font-semibold text-sm sm:text-base md:text-lg text-stone-900 tracking-tight">
            LikeHome
          </span>
          <span className="hidden md:inline text-xs text-stone-500 font-normal">
            by SuiteSpot
          </span>
        </Link>

        {/* Nav Links */}
        <nav className="flex items-center space-x-3 sm:space-x-6 text-xs sm:text-sm font-medium text-stone-600">
          <Link href="/" className="hover:text-stone-900 transition-colors">Explore</Link>
          <Link href="/bookings" className="hover:text-stone-900 transition-colors whitespace-nowrap">My Bookings</Link>
        </nav>

        {/* Auth Buttons */}
        <div className="flex items-center space-x-1.5 sm:space-x-3 shrink-0">
          <Link href="/login">
            <span className="text-xs sm:text-sm font-medium text-stone-600 hover:text-stone-900 px-1 py-1 whitespace-nowrap">
              Sign In
            </span>
          </Link>
          <Link href="/register">
            <Button size="sm" className="bg-stone-900 text-stone-50 hover:bg-stone-800 text-xs sm:text-sm px-2.5 sm:px-3 h-8 sm:h-9 whitespace-nowrap">
              Get Started
            </Button>
          </Link>
        </div>
      </div>
    </header>
  );
}