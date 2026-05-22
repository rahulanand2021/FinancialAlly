"use client";

import { useEffect, useRef, useState } from "react";

/** Applies a transient CSS class ("flash-up" / "flash-down") for ~500ms
 *  whenever `value` changes in the corresponding direction. */
export function useFlashOnChange(value: number | undefined): string {
  const [cls, setCls] = useState("");
  const prevRef = useRef<number | undefined>(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;
    if (value === undefined || prev === undefined || value === prev) return;

    const next = value > prev ? "flash-up" : "flash-down";
    setCls(next);

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCls(""), 500);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [value]);

  return cls;
}
