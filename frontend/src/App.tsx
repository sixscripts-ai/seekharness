import { BrowserRouter as Router, Routes, Route, useLocation } from "react-router-dom";
import SiteHeader from "@/components/SiteHeader";
import Home from "@/pages/Home";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import Providers from "@/pages/Providers";
import NewBattle from "@/pages/NewBattle";
import CustomBattle from "@/pages/CustomBattle";
import LiveBattle from "@/pages/LiveBattle";
import Leaderboard from "@/pages/Leaderboard";
import History from "@/pages/History";
import { useEffect } from "react";
import { subscribeSystemTheme } from "@/lib/theme";

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
    <>
      <SiteHeader />
      <main
        className={[
          fullWidth ? "px-0 py-0" : "mx-auto max-w-[1560px] px-6 py-8",
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
          <Route path="/keys" element={<Providers />} />
          <Route path="/battles" element={<History />} />
          <Route path="/history" element={<History />} />
          <Route path="/battles/new" element={<NewBattle />} />
          <Route path="/battles/custom" element={<CustomBattle />} />
          <Route path="/battles/:id" element={<LiveBattle />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="*" element={<div className="p-8 text-center text-zinc-400">404 — Not found</div>} />
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
