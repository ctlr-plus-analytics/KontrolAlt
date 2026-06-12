"use client";

import { useTour } from "./TourContext";

export function WelcomeModal() {
  const { isWelcomeOpen, markWelcomeSeen, closeWelcome, startTour } = useTour();

  if (!isWelcomeOpen) return null;

  function handleStartTour() {
    markWelcomeSeen();
    closeWelcome();
    startTour("dashboard");
  }

  function handleSkip() {
    markWelcomeSeen();
    closeWelcome();
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[9998] bg-black/50 backdrop-blur-sm"
        onClick={handleSkip}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-title"
      >
        <div
          className="w-full max-w-md rounded-2xl border border-[#C9A84C]/20 bg-[#1A1A2E] p-8 shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="mb-2 text-[11px] font-bold uppercase tracking-widest text-[#C9A84C]/60">
            First Time Here?
          </div>
          <h2
            id="welcome-title"
            className="mb-4 text-2xl font-bold tracking-tight text-[#F7F4EE]"
          >
            Welcome to KontrolAlt
          </h2>
          <p className="mb-7 text-sm leading-relaxed text-[#F7F4EE]/70">
            KontrolAlt is an intelligence and discovery engine for alternative
            media channels on Rumble and Substack. Use it to find, filter, and
            evaluate creators by engagement, growth velocity, and affiliation
            status.
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={handleStartTour}
              className="rounded-lg bg-[#C9A84C] px-5 py-2.5 text-sm font-bold text-[#1A1A2E] transition-opacity hover:opacity-90"
            >
              Start Tour
            </button>
            <button
              onClick={handleSkip}
              className="text-sm text-[#F7F4EE]/40 transition-colors hover:text-[#F7F4EE]/70"
            >
              Skip for now
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
