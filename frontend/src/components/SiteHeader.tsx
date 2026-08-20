import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { useEffect, useState } from "react";

const LINKS = [
  { href: "/", label: "Arena" },
  { href: "/battles/new", label: "New Battle" },
  { href: "/battles/custom", label: "Custom" },
  { href: "/providers", label: "Keys" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/history", label: "History" },
];

export default function SiteHeader() {
  const { user, logout, init } = useAuth();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const loc = useLocation();
  const battle = loc.pathname === "/battles/new" || loc.pathname === "/battles/custom" || loc.pathname.startsWith("/battles/");

  useEffect(() => { init(); }, [init]);

  return (
    <header className={`sticky top-0 z-50 border-b border-border ${battle ? "bg-background" : "bg-background/80 backdrop-blur"}`}>
      <div className="mx-auto flex h-14 max-w-[1360px] items-center justify-between px-6">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2.5">
            <div className={`grid h-7 w-7 place-items-center bg-accent text-[13px] font-bold text-accent-fg ${battle ? "rounded-none" : "rounded-md"}`}>A</div>
            <span className={battle ? "text-[14px] font-semibold uppercase tracking-[0.12em]" : "text-[14px] font-semibold tracking-[-0.01em]"}>{battle ? "Arena" : "Agent Arena"}</span>
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {LINKS.map(l => {
              const active = loc.pathname === l.href || (l.href !== "/" && loc.pathname.startsWith(l.href));
              return (
                <Link key={l.href} to={l.href} className={`navlink ${active ? "active" : ""}`}>
                  {l.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {user ? (
            <>
              <span className="hidden text-[12px] text-muted sm:block">{user.email || user.name || user.$id.slice(0, 8)}</span>
              <button
                onClick={async () => { await logout(); nav("/"); }}
                className="btn btn-ghost h-8 px-3 text-[12px]"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="navlink">Log in</Link>
              <Link to="/signup" className="btn btn-primary h-8 px-4 text-[12px]">Sign up</Link>
            </>
          )}
          <button onClick={() => setOpen(!open)} aria-label="Menu" className="grid h-8 w-8 place-items-center rounded-md border border-border text-[14px] md:hidden">☰</button>
        </div>
      </div>
      {open && (
        <div className="space-y-1 border-t border-border bg-background px-4 py-3 md:hidden">
          {LINKS.map(l => (
            <Link key={l.href} to={l.href} onClick={() => setOpen(false)} className="block rounded-md px-2 py-2 text-[13px] hover:bg-surface2">
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
