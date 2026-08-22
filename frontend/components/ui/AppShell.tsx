import Link from "next/link";
import type { ReactNode } from "react";

export type AppShellNavItem = { href: string; label: string; icon: ReactNode };

type IdentityHeader = {
  title?: never;
  greeting: string;
  name: string;
  avatar?: ReactNode;
};

type TitleHeader = {
  title: string;
  greeting?: never;
  name?: never;
  avatar?: never;
};

type AppShellProps = (IdentityHeader | TitleHeader) & {
  children: ReactNode;
  inboxHref: string;
  inboxLabel: string;
  inboxIcon?: ReactNode;
  unreadCount: number;
  navItems: AppShellNavItem[];
  activeHref: string;
  languageSwitch?: ReactNode;
};

export function AppShell({
  children,
  title,
  greeting,
  name,
  avatar = null,
  inboxHref,
  inboxLabel,
  inboxIcon = null,
  unreadCount,
  navItems,
  activeHref,
  languageSwitch = null,
}: AppShellProps) {
  return (
    <div className="mx-auto flex min-h-screen max-w-[430px] flex-col bg-bg">
      <header className="flex items-center gap-2 px-5 pb-2 pt-4">
        {title ? (
          <h1 className="min-w-0 flex-1 text-xl font-bold text-ink">{title}</h1>
        ) : (
          <>
            <span className="text-2xl" aria-hidden="true">{avatar}</span>
            <div className="min-w-0 flex-1 text-center">
              <p className="m-0 text-sm text-inkMuted">{greeting}</p>
              <p className="m-0 text-xl font-bold text-ink">{name}</p>
            </div>
          </>
        )}
        {languageSwitch}
        <Link
          className="relative grid min-h-11 min-w-11 place-items-center rounded-control border border-border bg-surface"
          href={inboxHref}
          aria-label={inboxLabel}
        >
          {inboxIcon}
          {unreadCount > 0 && (
            <span className="absolute -right-1 -top-1 min-w-5 rounded-chip bg-danger px-1 text-center text-xs font-bold text-ink-inverse">
              {unreadCount}
            </span>
          )}
        </Link>
      </header>
      <main className="flex-1 px-5 py-1">{children}</main>
      <nav className="sticky bottom-0 flex border-t border-border bg-bg px-2 py-2">
        {navItems.map((item) => (
          <Link
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
      </nav>
    </div>
  );
}
