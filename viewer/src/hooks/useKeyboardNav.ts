import { useEffect } from "react";

interface Handlers {
  onDown: () => void; // j
  onUp: () => void; // k
  onOpen: () => void; // Enter
  onSearch: () => void; // /
  onEscape: () => void; // Esc
}

// Global keyboard nav: j/k rows, Enter opens drawer, / focuses search, Esc closes.
// Ignores keystrokes while typing in an input/textarea (except Escape).
export function useKeyboardNav(handlers: Handlers) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const typing =
        el.tagName === "INPUT" ||
        el.tagName === "TEXTAREA" ||
        el.isContentEditable;

      if (e.key === "Escape") {
        handlers.onEscape();
        return;
      }
      if (typing) return;

      switch (e.key) {
        case "j":
          e.preventDefault();
          handlers.onDown();
          break;
        case "k":
          e.preventDefault();
          handlers.onUp();
          break;
        case "Enter":
          e.preventDefault();
          handlers.onOpen();
          break;
        case "/":
          e.preventDefault();
          handlers.onSearch();
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handlers]);
}
