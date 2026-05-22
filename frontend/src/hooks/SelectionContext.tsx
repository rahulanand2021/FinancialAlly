"use client";

import { createContext, ReactNode, useContext, useState } from "react";

interface SelectionContextValue {
  selectedTicker: string | null;
  selectTicker: (ticker: string) => void;
}

const SelectionContext = createContext<SelectionContextValue | null>(null);

export function SelectionProvider({
  children,
  initial = null,
}: {
  children: ReactNode;
  initial?: string | null;
}) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(initial);
  return (
    <SelectionContext.Provider
      value={{ selectedTicker, selectTicker: setSelectedTicker }}
    >
      {children}
    </SelectionContext.Provider>
  );
}

export function useSelection(): SelectionContextValue {
  const ctx = useContext(SelectionContext);
  if (!ctx) {
    throw new Error("useSelection must be used inside a SelectionProvider");
  }
  return ctx;
}
