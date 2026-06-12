"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { useAuth } from "@/hooks/useAuth";

export type TourId = "dashboard" | "channel-detail" | "admin";

interface TourStorage {
  hasSeenWelcome: boolean;
  completedTours: TourId[];
  skippedTours: TourId[];
}

interface TourContextValue {
  // state
  isAdmin: boolean;
  isHydrated: boolean;
  hasSeenWelcome: boolean;
  isWelcomeOpen: boolean;
  activeTourId: TourId | null;
  isRunning: boolean;
  // welcome actions
  markWelcomeSeen: () => void;
  openWelcome: () => void;
  closeWelcome: () => void;
  // tour actions
  startTour: (id: TourId) => void;
  stopTour: () => void;
  setRunning: (v: boolean) => void;
  markTourComplete: (id: TourId) => void;
  markTourSkipped: (id: TourId) => void;
  resetTour: (id: TourId) => void;
  resetAllTours: () => void;
  hasDoneTour: (id: TourId) => boolean;
}

const STORAGE_KEY = "kontrolalt_tour_v1";

const DEFAULT_STORAGE: TourStorage = {
  hasSeenWelcome: false,
  completedTours: [],
  skippedTours: [],
};

function readStorage(): TourStorage {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STORAGE;
    const parsed = JSON.parse(raw) as Partial<TourStorage>;
    return {
      hasSeenWelcome: parsed.hasSeenWelcome ?? false,
      completedTours: parsed.completedTours ?? [],
      skippedTours: parsed.skippedTours ?? [],
    };
  } catch {
    return DEFAULT_STORAGE;
  }
}

function writeStorage(data: TourStorage) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // storage full or unavailable — ignore
  }
}

const TourContext = createContext<TourContextValue | null>(null);

export function TourProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  // persisted state (mirrors localStorage)
  const [hasSeenWelcome, setHasSeenWelcome] = useState(false);
  const [completedTours, setCompletedTours] = useState<TourId[]>([]);
  const [skippedTours, setSkippedTours] = useState<TourId[]>([]);

  // runtime state
  const [activeTourId, setActiveTourId] = useState<TourId | null>(null);
  const [isRunning, setIsRunningState] = useState(false);
  const [isWelcomeOpen, setIsWelcomeOpen] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);

  // isAdmin — mirrors TopBar.tsx logic exactly
  const isAdmin = (() => {
    if (!user) return false;
    const appRole = user.app_metadata?.role;
    const appAdmin = user.app_metadata?.is_admin;
    const userRole = user.user_metadata?.role;
    const userAdmin = user.user_metadata?.is_admin;
    return (
      appRole === "admin" ||
      appAdmin === true ||
      appAdmin === "true" ||
      userRole === "admin" ||
      userAdmin === true ||
      userAdmin === "true"
    );
  })();

  // hydrate from localStorage once user is known
  useEffect(() => {
    const saved = readStorage();
    // localStorage must be read in an effect (no window during SSR); React 19 batches these.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHasSeenWelcome(saved.hasSeenWelcome);
    setCompletedTours(saved.completedTours);
    setSkippedTours(saved.skippedTours);
    setIsHydrated(true);
    if (user && !saved.hasSeenWelcome) {
      setIsWelcomeOpen(true);
    }
  }, [user]);

  // sync persisted state to localStorage
  useEffect(() => {
    if (!isHydrated) return;
    writeStorage({ hasSeenWelcome, completedTours, skippedTours });
  }, [hasSeenWelcome, completedTours, skippedTours, isHydrated]);

  const markWelcomeSeen = useCallback(() => setHasSeenWelcome(true), []);
  const openWelcome = useCallback(() => setIsWelcomeOpen(true), []);
  const closeWelcome = useCallback(() => setIsWelcomeOpen(false), []);

  const startTour = useCallback((id: TourId) => {
    setActiveTourId(id);
    setIsRunningState(false); // TourManager polls for DOM readiness, then calls setRunning(true)
  }, []);

  const stopTour = useCallback(() => {
    setActiveTourId(null);
    setIsRunningState(false);
  }, []);

  const setRunning = useCallback((v: boolean) => setIsRunningState(v), []);

  const markTourComplete = useCallback((id: TourId) => {
    setCompletedTours((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setSkippedTours((prev) => prev.filter((t) => t !== id));
  }, []);

  const markTourSkipped = useCallback((id: TourId) => {
    setSkippedTours((prev) => (prev.includes(id) ? prev : [...prev, id]));
  }, []);

  const resetTour = useCallback((id: TourId) => {
    setCompletedTours((prev) => prev.filter((t) => t !== id));
    setSkippedTours((prev) => prev.filter((t) => t !== id));
  }, []);

  const resetAllTours = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    setHasSeenWelcome(false);
    setCompletedTours([]);
    setSkippedTours([]);
    setActiveTourId(null);
    setIsRunningState(false);
    if (user) setIsWelcomeOpen(true);
  }, [user]);

  const hasDoneTour = useCallback(
    (id: TourId) => completedTours.includes(id) || skippedTours.includes(id),
    [completedTours, skippedTours]
  );

  return (
    <TourContext.Provider
      value={{
        isAdmin,
        isHydrated,
        hasSeenWelcome,
        isWelcomeOpen,
        activeTourId,
        isRunning,
        markWelcomeSeen,
        openWelcome,
        closeWelcome,
        startTour,
        stopTour,
        setRunning,
        markTourComplete,
        markTourSkipped,
        resetTour,
        resetAllTours,
        hasDoneTour,
      }}
    >
      {children}
    </TourContext.Provider>
  );
}

export function useTour(): TourContextValue {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error("useTour must be used within TourProvider");
  return ctx;
}
