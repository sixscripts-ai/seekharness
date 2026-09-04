import { BrowserRouter as Router, Routes, Route, useLocation } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import QuantumBackground from "@/components/QuantumBackground";
import { useEffect, lazy, Suspense } from "react";
import { subscribeSystemTheme } from "@/lib/theme";

const Home = lazy(() => import("@/pages/Home"));
const Login = lazy(() => import("@/pages/Login"));
const Signup = lazy(() => import("@/pages/Signup"));
const Providers = lazy(() => import("@/pages/Providers"));
const NewBattle = lazy(() => import("@/pages/NewBattle"));
const CustomBattle = lazy(() => import("@/pages/CustomBattle"));
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
        <span className="font-mono text-xs text-cyan-400/70 tracking-wider uppercase">Loading surface...</span>
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

function AppShell() {
  const loc = useLocation();
  const fullWidth = isFullWidthPath(loc.pathname);
  const liveBattle = isLiveBattlePath(loc.pathname);

  useEffect(() => {
    document.documentElement.classList.add("theme-void");
    return () => document.documentElement.classList.remove("theme-void");
  }, []);

  return (
    <div className="relative min-h-screen text-slate-100 selection:bg-cyan-500/30 selection:text-cyan-200">
      <QuantumBackground />
      <div className="relative z-10">
        <SiteHeader />
        <main
          className={[
            fullWidth ? "px-0 py-0" : "mx-auto max-w-[1560px] px-6 py-8",
            liveBattle ? "meticulous-ignore" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/providers" element={<Providers />} />
            <Route path="/keys" element={<Providers />} />
            <Route path="/battles" element={<History />} />
            <Route path="/history" element={<History />} />
            <Route path="/battles/new" element={<NewBattle />} />
            <Route path="/battles/custom" element={<CustomBattle />} />
            <Route path="/battles/:id" element={<LiveBattle />} />
            <Route path="/leaderboard" element={<Leaderboard />} />
            <Route path="/targets" element={<Targets />} />
            <Route path="/targets/:id" element={<TargetDetail />} />
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
