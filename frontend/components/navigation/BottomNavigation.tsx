"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { SignOutButton } from "../auth/SignOutButton";

export type NavigationItem = {
  href: string;
  label: string;
  icon: ReactNode;
};

export function BottomNavigation({
  items,
  activeHref,
}: {
  items: NavigationItem[];
  activeHref: string;
}) {
  return (
    <nav className="sticky bottom-0 flex border-t border-border bg-bg px-2 py-2">
      {items.map((item) => (
        <Link
          aria-current={item.href === activeHref ? "page" : undefined}
          className={`flex min-h-11 flex-1 flex-col items-center justify-center gap-1 text-xs font-bold ${
            item.href === activeHref ? "text-primary" : "text-inkMuted"
          }`}
          href={item.href}
          key={item.href}
        >
          {item.icon}
          <span>{item.label}</span>
        </Link>
      ))}
      <SignOutButton />
    </nav>
  );
}
