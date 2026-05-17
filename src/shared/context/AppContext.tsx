import { useCallback, useState } from "react";
import type { Lead, View } from "../../types";
import { ONBOARDING_KEY } from "../lib/leadUtils";

export function useAppShellState() {
  const [view, setView] = useState<View>("dashboard");
  const [sel, setSel] = useState<Lead | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(() => localStorage.getItem(ONBOARDING_KEY) !== "done");
  const [applyDraft, setApplyDraft] = useState("");
  const [applyAutoFocus, setApplyAutoFocus] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [reevaluating, setReevaluating] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [scanErr, setScanErr] = useState<string | null>(null);

  const closeDrawer = useCallback(() => setSel(null), []);
  const focusApplyView = useCallback(() => {
    setView("apply");
    setApplyAutoFocus(true);
  }, []);
  const openSettings = useCallback(() => setShowSettings(true), []);
  const openSetupGuide = useCallback(() => {
    localStorage.removeItem(ONBOARDING_KEY);
    setShowOnboarding(true);
  }, []);

  return {
    view,
    setView,
    sel,
    setSel,
    showSettings,
    setShowSettings,
    showOnboarding,
    setShowOnboarding,
    applyDraft,
    setApplyDraft,
    applyAutoFocus,
    setApplyAutoFocus,
    scanning,
    setScanning,
    reevaluating,
    setReevaluating,
    cleaning,
    setCleaning,
    scanErr,
    setScanErr,
    closeDrawer,
    focusApplyView,
    openSettings,
    openSetupGuide,
  };
}
