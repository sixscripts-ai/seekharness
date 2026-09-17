import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Menu, Plus, Search, Settings, Swords, Shield, Trophy } from "lucide-react";
import { useAuth } from "@/lib/auth";

interface SiteHeaderProps {
  onToggleSidebar?: () => void;
}

export default function SiteHeader({ onToggleSidebar }: SiteHeaderProps) {
  const { user, init } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => { void init(); }, [init]);

  const active = (href: string) => href === "/battles"
    ? location.pathname === "/" || location.pathname === "/history" || location.pathname.startsWith("/battles")
    : href === "/challenges"
      ? /^\/(challenges|targets)(\/|$)/.test(location.pathname)
      : location.pathname.startsWith(href);

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    if (location.pathname.startsWith("/challenges")) {
      const section = location.pathname === "/challenges/user" ? "user" : "official";
      navigate(`/challenges/${section}?q=${encodeURIComponent(searchQuery.trim())}`);
    } else {
      navigate(`/battles?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.08] bg-[#07080B]/80 backdrop-blur-xl">
      <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6">
        
        {/* Left: Mobile Drawer Trigger + Breadcrumb Tabs */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onToggleSidebar}
            className="rounded-lg p-2 text-slate-400 hover:bg-white/[0.06] hover:text-white lg:hidden"
            aria-label="Toggle navigation menu"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Desktop segmented view pill */}
          <nav aria-label="Quick tabs" className="hidden sm:flex items-center gap-1 rounded-xl border border-white/[0.08] bg-white/[0.03] p-1 shadow-inner">
            <Link
              to="/battles"
              aria-current={active("/battles") ? "page" : undefined}
              className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                active("/battles")
                  ? "bg-white/[0.09] text-white shadow-[inset_0_1px_0_0_rgba(255,255,255,0.15)] border border-white/10"
                  : "text-slate-400 hover:text-slate-200 border border-transparent"
              }`}
            >
              <Swords className="h-3.5 w-3.5" />
              <span>Battles</span>
            </Link>
            <Link
              to="/challenges/official"
              aria-current={active("/challenges") ? "page" : undefined}
              className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                active("/challenges")
                  ? "bg-white/[0.09] text-white shadow-[inset_0_1px_0_0_rgba(255,255,255,0.15)] border border-white/10"
                  : "text-slate-400 hover:text-slate-200 border border-transparent"
              }`}
            >
              <Shield className="h-3.5 w-3.5" />
              <span>Challenges</span>
            </Link>
            <Link
              to="/leaderboard"
              aria-current={active("/leaderboard") ? "page" : undefined}
              className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                active("/leaderboard")
                  ? "bg-white/[0.09] text-white shadow-[inset_0_1px_0_0_rgba(255,255,255,0.15)] border border-white/10"
                  : "text-slate-400 hover:text-slate-200 border border-transparent"
              }`}
            >
              <Trophy className="h-3.5 w-3.5" />
              <span>Leaderboard</span>
            </Link>
          </nav>
        </div>

        {/* Center: Search Arena (Cmd+K) */}
        <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-md hidden md:block">
          <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search Arena (Cmd+K)"
            aria-label="Search Arena"
            className="luxe-input w-full pl-9 pr-14 py-1.5 text-xs placeholder:text-slate-500"
          />
          <kbd className="pointer-events-none absolute right-2.5 top-2 hidden h-5 select-none items-center gap-0.5 rounded border border-white/10 bg-white/5 px-1.5 font-mono text-[10px] font-medium text-slate-400 sm:flex">
            ⌘K
          </kbd>
        </form>

        {/* Right: Actions */}
        <div className="flex items-center gap-3">
          <Link
            to="/battles/new"
            className="btn-luxe-primary h-9 px-3.5 text-xs gap-1.5"
          >
            <Plus className="h-3.5 w-3.5 text-cyan-300" />
            <span className="font-semibold">New Battle</span>
          </Link>

          <Link
            to="/settings"
            aria-label="Settings"
            className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-2 text-slate-400 hover:bg-white/[0.08] hover:text-white transition-colors"
            title="Settings & Model Registry"
          >
            <Settings className="h-4 w-4" />
          </Link>

          {user ? (
            <div className="relative flex h-8 w-8 items-center justify-center rounded-full border border-white/20 bg-gradient-to-tr from-cyan-500/20 to-purple-500/20 text-xs font-bold text-white shadow-inner">
              {user.name ? user.name[0].toUpperCase() : "U"}
            </div>
          ) : (
            <Link
              to="/login"
              className="text-xs font-medium text-slate-300 hover:text-white px-2 py-1"
            >
              Sign in
            </Link>
          )}
        </div>

      </div>
    </header>
  );
}
