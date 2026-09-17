import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { LogOut, Menu, Plus, Settings, X } from "lucide-react";
import { useAuth } from "@/lib/auth";

const navigation = [
  { href: "/battles", label: "Battles" },
  { href: "/challenges", label: "Challenges" },
  { href: "/leaderboard", label: "Leaderboard" },
];

export default function SiteHeader() {
  const { user, logout, init } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => { void init(); }, [init]);
  useEffect(() => { setMenuOpen(false); }, [location.pathname, location.search]);

  const active = (href: string) => href === "/battles"
    ? location.pathname === "/" || location.pathname === "/history" || location.pathname.startsWith("/battles")
    : href === "/challenges"
      ? /^\/(challenges|targets)(\/|$)/.test(location.pathname)
      : location.pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-[#08090D]/95 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-3 px-4 sm:gap-4 sm:px-6">
        <Link to="/battles" className="mr-auto flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-white md:mr-6">
          <span aria-hidden="true" className="grid h-8 w-8 place-items-center rounded-lg border border-cyan-400/40 bg-cyan-400/10 text-sm text-cyan-300">S</span>
          <span>SeekHarness</span>
        </Link>
        <nav aria-label="Main navigation" className="mr-auto hidden items-center gap-1 md:flex">
          {navigation.map(link => <Link key={link.href} to={link.href} aria-current={active(link.href) ? "page" : undefined}
            className={`rounded-lg px-3 py-2 text-sm transition-colors ${active(link.href) ? "bg-white/5 text-cyan-300" : "text-slate-400 hover:text-white"}`}>{link.label}</Link>)}
        </nav>
        <Link to="/battles/new" className="flex min-h-9 items-center gap-1.5 rounded-lg bg-cyan-300 px-3 text-sm font-semibold text-slate-950 hover:bg-cyan-200">
          <Plus className="h-4 w-4" aria-hidden="true" /><span className="hidden sm:inline">New battle</span><span className="sm:hidden">New</span>
        </Link>
        <Link to="/settings" aria-label="Settings" aria-current={location.pathname.startsWith("/settings") ? "page" : undefined} className="hidden rounded-lg p-2 text-slate-400 hover:text-white md:block" title="Settings">
          <Settings className="h-5 w-5" />
        </Link>
        {user ? <button type="button" title="Log out" aria-label="Log out" onClick={async () => { await logout(); navigate("/battles"); }} className="hidden rounded-lg p-2 text-slate-400 hover:text-white md:block"><LogOut className="h-4 w-4" /></button>
          : <Link to="/login" className="hidden text-sm text-slate-300 hover:text-white md:block">Log in</Link>}
        <button type="button" aria-label={menuOpen ? "Close navigation" : "Open navigation"} aria-expanded={menuOpen} aria-controls="mobile-navigation" onClick={() => setMenuOpen(!menuOpen)} onKeyDown={event => { if (event.key === "Escape") setMenuOpen(false); }} className="rounded-lg p-2 text-slate-300 md:hidden">
          {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>
      {menuOpen && <nav id="mobile-navigation" aria-label="Mobile navigation" className="space-y-1 border-t border-white/10 px-4 py-3 md:hidden">
        {[...navigation, { href: "/settings", label: "Settings" }].map(link => <Link key={link.href} to={link.href} aria-current={active(link.href) ? "page" : undefined} className={`block rounded-lg px-3 py-3 text-sm ${active(link.href) ? "bg-white/5 text-cyan-300" : "text-slate-300"}`}>{link.label}</Link>)}
        {user ? <button type="button" className="px-3 py-3 text-sm text-slate-400" onClick={async () => { await logout(); setMenuOpen(false); navigate("/battles"); }}>Log out</button> : <Link to="/login" className="block px-3 py-3 text-sm text-slate-300">Log in</Link>}
      </nav>}
    </header>
  );
}
