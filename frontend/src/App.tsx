import { BrowserRouter as Router, Routes, Route, useLocation } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import Home from "@/pages/Home";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import Providers from "@/pages/Providers";
import NewBattle from "@/pages/NewBattle";
import LiveBattle from "@/pages/LiveBattle";
import Leaderboard from "@/pages/Leaderboard";
import History from "@/pages/History";
import { useEffect } from "react";
import { subscribeSystemTheme } from "@/lib/theme";

function isBattlePath(pathname: string): boolean {
  return pathname === "/battles/new" || pathname.startsWith("/battles/");
}

// The live battle view streams non-deterministic model/harness output (SSE),
// so we exclude it from Meticulous visual diffs via the `meticulous-ignore`
// class. The setup form at /battles/new is stable and stays covered.
function isLiveBattlePath(pathname: string): boolean {
  return pathname.startsWith("/battles/") && pathname !== "/battles/new";
}

function AppShell() {
  const loc = useLocation();
  const battle = isBattlePath(loc.pathname);
  const liveBattle = isLiveBattlePath(loc.pathname);

  useEffect(() => {
    document.documentElement.classList.add("theme-void");
    return () => document.documentElement.classList.remove("theme-void");
  }, []);

  return (
    <>
      <SiteHeader />
      <main
        className={[
          battle ? "px-0 py-0" : "mx-auto max-w-[1360px] px-6 py-8",
          liveBattle ? "meticulous-ignore" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/providers" element={<Providers />} />
          <Route path="/battles/new" element={<NewBattle />} />
          <Route path="/battles/:id" element={<LiveBattle />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/history" element={<History />} />
          <Route path="*" element={<div className="p-8 text-center">404 — Not found</div>} />
        </Routes>
      </main>
    </>
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
