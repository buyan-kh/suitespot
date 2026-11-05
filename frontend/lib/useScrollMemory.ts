"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

// Task 1.7.2 - keep the user's scroll position on the results page.
// Usage: useScrollMemory(searchParams.toString(), !loading);

let cameBackOrForward = false;
if (typeof window !== "undefined") {
  window.addEventListener("popstate", () => {
    cameBackOrForward = true;
  });
}

function firstLoadWasBackOrReload(): boolean {
  try {
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    return nav?.type === "back_forward" || nav?.type === "reload";
  } catch {
    return false;
  }
}

export function useScrollMemory(key: string, ready: boolean) {
  const pathname = usePathname();
  const storageKey = `scroll:${pathname}?${key}`;
  const readyRef = useRef(ready);
  const sawLoading = useRef(false);
  const shouldRestore = useRef(cameBackOrForward || firstLoadWasBackOrReload());
  const isFirstKey = useRef(true);

  useEffect(() => {
    readyRef.current = ready;
    if (!ready) sawLoading.current = true;
  }, [ready]);

  useEffect(() => {
    if (cameBackOrForward) {
      shouldRestore.current = true;
      cameBackOrForward = false;
    }
  }, [storageKey]);

  useEffect(() => {
    let frame = 0;
    const save = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!readyRef.current) return;
        try {
          sessionStorage.setItem(storageKey, String(Math.round(window.scrollY)));
        } catch {}
      });
    };
    window.addEventListener("scroll", save, { passive: true });
    return () => {
      window.removeEventListener("scroll", save);
      cancelAnimationFrame(frame);
    };
  }, [storageKey]);

  useEffect(() => {
    if (isFirstKey.current) {
      isFirstKey.current = false;
      return;
    }
    const root = document.documentElement;
    root.style.minHeight = `${root.scrollHeight}px`;
    const timer = window.setTimeout(() => {
      root.style.minHeight = "";
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [storageKey]);

  useEffect(() => {
    if (!ready) return;
    const skipSave = !sawLoading.current || shouldRestore.current;
    const frame = requestAnimationFrame(() => {
      document.documentElement.style.minHeight = "";
      if (skipSave) return;
      try {
        sessionStorage.setItem(storageKey, String(Math.round(window.scrollY)));
      } catch {}
    });
    return () => cancelAnimationFrame(frame);
  }, [ready, storageKey]);

  useEffect(() => {
    return () => {
      document.documentElement.style.minHeight = "";
    };
  }, []);

  useEffect(() => {
    if (!ready || !sawLoading.current || !shouldRestore.current) return;
    shouldRestore.current = false;
    let saved: number | null = null;
    try {
      const raw = sessionStorage.getItem(storageKey);
      saved = raw === null ? null : Number(raw);
    } catch {
      saved = null;
    }
    if (saved === null || Number.isNaN(saved)) return;
    const y = saved;
    requestAnimationFrame(() => window.scrollTo(0, y));
  }, [ready, storageKey]);
}