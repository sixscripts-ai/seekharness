import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import SiteSidebar from "@/components/SiteSidebar";
import QuantumBackground from "@/components/QuantumBackground";
import { useEffect, useState, lazy, Suspense } from "react";
import { subscribeSystemTheme } from "@/lib/theme";
import { legacyCustomUrl, legacyTargetUrl } from "@/lib/challengeNavigation";

const Login = lazy(() => import("@/pages/Login"));
const Signup = lazy(() => import("@/pages/Signup"));
const Providers = lazy(() => import("@/pages/Providers"));
const NewBattle = lazy(() => import("@/pages/NewBattle"));
const LiveBattle = lazy(() => import("@/pages/LiveBattle"));
const Leaderboard = lazy(() => import("@/pages/Leaderboard"));
const History = lazy(() => import("@/pages/History"));
const Targets = lazy(() => import("@/pages/Targets"));
const TargetDetail = lazy(() => import("@/pages/TargetDetail"));

function PageLoader() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="relative flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500/20 border-t-cyan-400" />
        <span className="text-sm text-slate-400">Loading…</span>
      </div>
    </div>
  );
}

function isFullWidthPath(pathname: string): boolean {
  return (
    pathname === "/" ||
    pathname === "/battles" ||
    pathname === "/history" ||
    pathname === "/battles/new" ||
    pathname === "/battles/custom" ||
    pathname === "/providers" ||
    pathname === "/keys" ||
    pathname.startsWith("/settings") ||
    pathname.startsWith("/challenges") ||
    pathname === "/leaderboard" ||
    pathname === "/targets" ||
    pathname.startsWith("/targets/") ||
    pathname.startsWith("/battles/")
  );
}

function isLiveBattlePath(pathname: string): boolean {
  return (
    pathname.startsWith("/battles/") &&
    pathname !== "/battles/new" &&
    pathname !== "/battles/custom" &&
    pathname !== "/battles"
  );
}

function LegacyCustomBattle() {
  const location = useLocation();
  return <Navigate replace to={legacyCustomUrl(location.search)} />;
}

function LegacyTargets() {
  const location = useLocation();
  return <Navigate replace to={legacyTargetUrl(location.pathname, location.search, location.hash)} />;
}

function DefaultChallenges() {
  const location = useLocation();
  return <Navigate replace to={`/challenges/official${location.search}${location.hash}`} />;
}

function AppShell() {
  const loc = useLocation();
  const fullWidth = isFullWidthPath(loc.pathname);
  const liveBattle = isLiveBattlePath(loc.pathname);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    document.documentElement.classList.add("theme-void");
    return () => document.documentElement.classList.remove("theme-void");
  }, []);

  return (
    <div className="relative min-h-screen text-slate-100 selection:bg-cyan-500/30 selection:text-cyan-200 luxe-canvas">
      <QuantumBackground />
      <SiteSidebar mobileOpen={mobileSidebarOpen} onCloseMobile={() => setMobileSidebarOpen(false)} />
      <div className="relative z-10 flex min-h-screen flex-col lg:pl-64">
        <SiteHeader onToggleSidebar={() => setMobileSidebarOpen(v => !v)} />
        <main
          className={[
            "flex-1",
            fullWidth ? "px-0 py-0" : "mx-auto w-full max-w-[1560px] px-6 py-8",
            liveBattle ? "meticulous-ignore" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<History />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/providers" element={<Providers />} />
            <Route path="/keys" element={<Providers />} />
            <Route path="/settings" element={<Providers />} />
            <Route path="/settings/models" element={<Providers />} />
            <Route path="/battles" element={<History />} />
            <Route path="/history" element={<History />} />
            <Route path="/battles/new" element={<NewBattle />} />
            <Route path="/battles/custom" element={<LegacyCustomBattle />} />
            <Route path="/battles/:id" element={<LiveBattle />} />
            <Route path="/leaderboard" element={<Leaderboard />} />
            <Route path="/targets" element={<LegacyTargets />} />
            <Route path="/targets/:id" element={<LegacyTargets />} />
            <Route path="/challenges" element={<DefaultChallenges />} />
            <Route path="/challenges/official" element={<Targets section="official" />} />
            <Route path="/challenges/user" element={<Targets section="user" />} />
            <Route path="/challenges/:id" element={<TargetDetail />} />
            <Route path="*" element={<div className="p-8 text-center text-zinc-400">404 — Not found</div>} />
          </Routes>
        </Suspense>
      </main>
      </div>
    </div>
  );
}

export default function App() {
  useEffect(() => {
    return subscribeSystemTheme();
  }, []);

  return (
    <Router>
      <AppShell />
    </Router>
  );
}
