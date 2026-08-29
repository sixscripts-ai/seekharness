import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Plus, LogOut } from "lucide-react";

const NAV_LINKS = [
  { href: "/", label: "Arena" },
  { href: "/battles", label: "Battles" },
  { href: "/providers", label: "Models" },
  { href: "/targets", label: "Targets" },
  { href: "/leaderboard", label: "Leaderboard" },
];

export default function SiteHeader() {
  const { user, logout, init } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const nav = useNavigate();
  const loc = useLocation();

  useEffect(() => {
    init();
  }, [init]);

  function isActive(href: string) {
    if (href === "/") return loc.pathname === "/";
    if (href === "/battles") {
      return (
        loc.pathname === "/battles" ||
        loc.pathname === "/history" ||
        (loc.pathname.startsWith("/battles/") &&
          loc.pathname !== "/battles/new" &&
          loc.pathname !== "/battles/custom")
      );
    }
    if (href === "/providers") {
      return loc.pathname === "/providers" || loc.pathname === "/keys";
    }
    return loc.pathname.startsWith(href);
  }

  return (
    <header className="sticky top-0 z-50 border-b border-[#1F1F22] bg-[#09090E]/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1560px] items-center justify-between px-4 sm:px-6">
        {/* Brand Logo & Core Nav */}
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-[13px] font-extrabold text-white shadow-[0_0_12px_rgba(255,0,160,0.4)] transition-transform group-hover:scale-105">
              A
            </div>
            <span className="text-sm font-extrabold tracking-wider text-white uppercase drop-shadow-[0_0_10px_rgba(255,0,160,0.25)]">
              Agent <span className="text-accent">Arena</span>
            </span>
          </Link>

          <nav className="hidden items-center gap-1.5 md:flex">
            {NAV_LINKS.map((link) => {
              const active = isActive(link.href);
              return (
                <Link
                  key={link.href}
                  to={link.href}
                  className={`mono rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
                    active
                      ? "bg-accent/15 text-accent border border-accent/30 shadow-[0_0_10px_rgba(255,0,160,0.2)]"
                      : "text-zinc-400 hover:text-white hover:bg-[#161619]"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Right Action Hub */}
        <div className="flex items-center gap-3">
          <Link
            to="/battles/new"
            className="btn btn-primary flex h-8 items-center gap-1.5 px-3.5 text-xs font-bold shadow-[0_0_14px_rgba(255,0,160,0.35)]"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Battle</span>
          </Link>

          <div className="h-4 w-px bg-[#26262A] mx-0.5 hidden sm:block" />

          {user ? (
            <div className="flex items-center gap-2.5">
              <span className="hidden mono text-[11px] text-zinc-400 max-w-[160px] truncate sm:block">
                {user.email || user.name || user.$id.slice(0, 8)}
              </span>
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  nav("/");
                }}
                className="mono flex h-8 items-center gap-1.5 rounded-lg border border-[#26262A] bg-[#0D0D0F] px-2.5 text-xs text-zinc-400 transition-colors hover:border-red-500/40 hover:text-red-400"
                title="Log out"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                to="/login"
                className="mono px-3 py-1.5 text-xs font-semibold text-zinc-400 hover:text-white"
              >
                Log in
              </Link>
              <Link
                to="/signup"
                className="mono rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-bold text-accent transition-all hover:bg-accent/20"
              >
                Sign up
              </Link>
            </div>
          )}

          {/* Mobile Menu Trigger */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle navigation menu"
            className="grid h-8 w-8 place-items-center rounded-lg border border-[#26262A] bg-[#0D0D0F] text-sm text-zinc-400 hover:text-white md:hidden"
          >
            ☰
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="space-y-1.5 border-t border-[#1F1F22] bg-[#09090E] px-4 py-3 md:hidden">
          {NAV_LINKS.map((link) => {
            const active = isActive(link.href);
            return (
              <Link
                key={link.href}
                to={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`mono block rounded-lg px-3 py-2 text-xs font-semibold ${
                  active
                    ? "bg-accent/15 text-accent font-bold"
                    : "text-zinc-400 hover:bg-[#161619] hover:text-white"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      )}
    </header>
  );
}
