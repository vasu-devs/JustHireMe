import { useEffect } from "react";

export function useKeyboardShortcuts(config: {
  onEscape: () => void;
  onCmdK: () => void;
  onCmdComma: () => void;
}) {
  const { onEscape, onCmdK, onCmdComma } = config;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (e.key === "Escape") {
        // Don't hijack Escape while the user is editing a field (e.g. the Form
        // Reader URL input or a select) — that would close the whole drawer and
        // discard their input. Let the field handle its own Escape.
        const target = e.target as HTMLElement | null;
        const tag = target?.tagName;
        const editing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable === true;
        if (!editing) onEscape();
      }
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onCmdK();
      }
      if (mod && e.key === ",") {
        e.preventDefault();
        onCmdComma();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onEscape, onCmdK, onCmdComma]);
}
