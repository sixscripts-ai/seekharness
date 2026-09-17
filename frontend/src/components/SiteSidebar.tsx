import { Link, useLocation, useNavigate } from "react-router-dom";
import { 
  Swords, 
  Shield, 
  Cpu, 
  Trophy, 
  LogOut, 
  LogIn, 
  Plus, 
  X
} from "lucide-react";
import { useAuth } from "@/lib/auth";

interface SiteSidebarProps {
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export default function SiteSidebar({ mobileOpen = false, onCloseMobile }: SiteSidebarProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const navItems = [
    { 
      href: "/battles", 
      label: "Battles", 
      icon: Swords, 
      active: location.pathname === "/" || location.pathname === "/battles" || location.pathname === "/history" || location.pathname.startsWith("/battles/")
    },
    { 
      href: "/challenges", 
      label: "Challenges", 
      icon: Shield, 
      active: location.pathname.startsWith("/challenges") || location.pathname.startsWith("/targets")
    },
    { 
      href: "/settings", 
      label: "Models & Keys", 
      icon: Cpu, 
      active: location.pathname.startsWith("/settings") || location.pathname === "/providers" || location.pathname === "/keys"
    },
    { 
      href: "/leaderboard", 
      label: "Leaderboard", 
      icon: Trophy, 
      active: location.pathname.startsWith("/leaderboard")
    },
  ];

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div 
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside 
        className={`fixed top-0 bottom-0 left-0 z-50 flex w-64 flex-col border-r border-white/[0.08] bg-[#08090E]/95 backdrop-blur-2xl transition-transform duration-300 ease-in-out lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        {/* Brand Header */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.08] px-5">
          <Link 
            to="/battles" 
            onClick={onCloseMobile}
            className="flex items-center gap-3 group"
          >
            <div className="relative grid h-9 w-9 place-items-center rounded-xl border border-white/20 bg-gradient-to-br from-white/10 to-white/5 text-white shadow-inner group-hover:border-cyan-400/50 transition-colors">
              <span className="font-display font-bold text-sm tracking-wider text-cyan-300">S</span>
              <div className="absolute -inset-0.5 rounded-xl bg-cyan-400/20 blur opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <div>
              <div className="font-display text-sm font-semibold tracking-tight text-white flex items-center gap-1.5">
                SeekHarness
              </div>
              <div className="text-[10px] font-medium uppercase tracking-widest text-slate-500">
                AI Arena
              </div>
            </div>
          </Link>

          {onCloseMobile && (
            <button 
              type="button" 
              onClick={onCloseMobile}
              className="rounded-lg p-1.5 text-slate-400 hover:text-white lg:hidden"
              aria-label="Close sidebar"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Quick Launch CTA */}
        <div className="p-4 pb-2">
          <Link
            to="/battles/new"
            onClick={onCloseMobile}
            className="btn-luxe-primary w-full flex items-center justify-center gap-2 group"
          >
            <Plus className="h-4 w-4 text-cyan-300 group-hover:rotate-90 transition-transform duration-200" />
            <span>New Battle</span>
          </Link>
        </div>

        {/* Primary Navigation */}
        <nav className="flex-1 space-y-1.5 px-3 py-3 overflow-y-auto" aria-label="Sidebar navigation">
          <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Workspaces
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                to={item.href}
                onClick={onCloseMobile}
                aria-current={item.active ? "page" : undefined}
                className={`group flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-xs font-medium transition-all ${
                  item.active
                    ? "bg-white/[0.08] text-white shadow-[inset_0_1px_0_0_rgba(255,255,255,0.14)] border border-white/10"
                    : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200 border border-transparent"
                }`}
              >
                <Icon className={`h-4 w-4 transition-colors ${item.active ? "text-cyan-300" : "text-slate-500 group-hover:text-slate-300"}`} />
                <span>{item.label}</span>
                {item.active && (
                  <div className="ml-auto h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#22d3ee]" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* System Status Pill */}
        <div className="p-3 mx-3 mb-2 rounded-xl border border-white/[0.06] bg-white/[0.02]">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-400">Modal MicroVMs</span>
            <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#34d399]" />
              Isolated
            </span>
          </div>
          <div className="mt-1.5 flex items-center justify-between text-[11px]">
            <span className="text-slate-400">Database</span>
            <span className="text-slate-300 font-mono text-[10px]">Neon Postgres</span>
          </div>
        </div>

        {/* User Account / Footer */}
        <div className="border-t border-white/[0.08] p-3">
          {user ? (
            <div className="flex items-center justify-between rounded-xl px-3 py-2 bg-white/[0.03]">
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-white">{user.name || "Arena Fighter"}</div>
                <div className="truncate text-[10px] text-slate-500">{user.email || user.$id}</div>
              </div>
              <button
                type="button"
                title="Log out"
                onClick={async () => {
                  await logout();
                  onCloseMobile?.();
                  navigate("/battles");
                }}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
                aria-label="Log out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <Link
              to="/login"
              onClick={onCloseMobile}
              className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 text-xs font-medium text-slate-300 hover:bg-white/[0.06] hover:text-white transition-colors"
            >
              <LogIn className="h-4 w-4" />
              <span>Sign In</span>
            </Link>
          )}
        </div>
      </aside>
    </>
  );
}
