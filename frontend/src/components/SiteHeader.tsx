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
    <header className="sticky top-0 z-50 border-b border-white/[0.08] bg-[#08090D]/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1560px] items-center justify-between px-4 sm:px-6">
        {/* Brand Logo & Title */}
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-cyan-400 via-blue-500 to-fuchsia-500 text-[14px] font-black text-white shadow-[0_0_16px_rgba(0,210,255,0.4)] transition-transform group-hover:scale-105">
            A
          </div>
          <span className="font-display text-sm font-extrabold tracking-wider text-white uppercase drop-shadow-[0_0_12px_rgba(0,210,255,0.25)]">
            Agent <span className="text-cyan-400">Arena</span>
          </span>
        </Link>

        {/* Floating Capsule Nav (Desktop) */}
        <nav className="hidden items-center md:flex">
          <div className="qos-nav-capsule">
            {NAV_LINKS.map((link) => {
              const active = isActive(link.href);
              return (
                <Link
                  key={link.href}
                  to={link.href}
                  className={`qos-nav-item ${active ? "qos-nav-item--active" : ""}`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
        </nav>

        {/* Right Action Hub */}
        <div className="flex items-center gap-3">
          <Link
            to="/battles/new"
            className="qos-btn-glow flex h-9 items-center gap-1.5 px-4 text-xs font-bold"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Battle</span>
          </Link>

          <div className="h-4 w-px bg-white/10 mx-1 hidden sm:block" />

          {user ? (
            <div className="flex items-center gap-2.5">
              <span className="hidden mono text-[11px] text-slate-400 max-w-[160px] truncate sm:block px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.08]">
                {user.email || user.name || user.$id.slice(0, 8)}
              </span>
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  nav("/");
                }}
                className="mono flex h-8 items-center gap-1.5 rounded-full border border-white/[0.08] bg-[#11141E] px-3 text-xs text-slate-400 transition-colors hover:border-red-500/40 hover:text-red-400"
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
                className="mono px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-white"
              >
                Log in
              </Link>
              <Link
                to="/signup"
                className="mono rounded-full border border-cyan-400/40 bg-cyan-400/10 px-3.5 py-1.5 text-xs font-bold text-cyan-400 transition-all hover:bg-cyan-400/20 shadow-[0_0_10px_rgba(0,210,255,0.2)]"
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
            className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-[#11141E] text-sm text-slate-400 hover:text-white md:hidden"
          >
            ☰
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="space-y-1.5 border-t border-white/[0.08] bg-[#0C0E15] px-4 py-3 md:hidden">
          {NAV_LINKS.map((link) => {
            const active = isActive(link.href);
            return (
              <Link
                key={link.href}
                to={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`mono block rounded-lg px-3 py-2 text-xs font-semibold ${
                  active
                    ? "bg-cyan-500/15 text-cyan-400 font-bold border border-cyan-500/30"
                    : "text-slate-400 hover:bg-[#161A27] hover:text-white"
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
