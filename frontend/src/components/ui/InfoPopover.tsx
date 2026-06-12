"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface InfoPopoverProps {
  content: string;
  dark?: boolean;
}

export function InfoPopover({ content, dark = false }: InfoPopoverProps) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleOutside = (e: MouseEvent) => {
      if (!btnRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const handleScroll = () => setOpen(false);
    document.addEventListener("mousedown", handleOutside);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [open]);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (open) { setOpen(false); return; }
    if (btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      const popupWidth = 224;
      setCoords({
        top: r.bottom + 8,
        left: Math.min(r.left, window.innerWidth - popupWidth - 8),
      });
      setOpen(true);
    }
  };

  const btnClass = dark
    ? `flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border text-[9px] font-bold transition-colors ${open ? "border-[#C9A84C]/80 text-[#C9A84C]" : "border-[#F7F4EE]/20 text-[#F7F4EE]/30 hover:border-[#C9A84C]/60 hover:text-[#C9A84C]/80 cursor-pointer"}`
    : `flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[9px] font-bold transition-colors ${open ? "border-[#C9A84C] text-[#C9A84C]" : "border-[#D8D2C8] text-[#A09A8E] hover:border-[#C9A84C] hover:text-[#C9A84C] cursor-pointer"}`;

  return (
    <>
      <button ref={btnRef} type="button" onClick={handleClick} aria-label="More information" className={btnClass}>
        i
      </button>
      {open && coords && createPortal(
        <div
          style={{ position: "fixed", top: coords.top, left: coords.left, zIndex: 9999 }}
          className="w-56 rounded-xl border border-[#E8E4DC] bg-white p-3 shadow-xl"
        >
          <p className="text-xs leading-5 text-[#6B6B6B]">{content}</p>
        </div>,
        document.body
      )}
    </>
  );
}
