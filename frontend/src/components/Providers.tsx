"use client";

import { TourProvider } from "@/components/tour/TourContext";
import { TourManager } from "@/components/tour/TourManager";
import { WelcomeModal } from "@/components/tour/WelcomeModal";

interface ProvidersProps {
  children: React.ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return (
    <TourProvider>
      <TourManager />
      <WelcomeModal />
      {children}
    </TourProvider>
  );
}
