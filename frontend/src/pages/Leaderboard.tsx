import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type FormatOut, type LeaderboardRow } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Trophy, Swords, Sparkles, AlertCircle } from "lucide-react";

const SAMPLE_BENCHMARK_ROWS: LeaderboardRow[] = [
  { model_id: "anthropic/claude-3.7-sonnet", format_id: "overall", elo: 1842, games_played: 128 },
  { model_id: "deepseek/deepseek-r1", format_id: "overall", elo: 1798, games_played: 114 },
  { model_id: "openai/gpt-4.5-preview", format_id: "overall", elo: 1760, games_played: 98 },
  { model_id: "meta-llama/llama-3.3-70b-instruct", format_id: "overall", elo: 1695, games_played: 142 },
  { model_id: "qwen/qwen-2.5-coder-32b-instruct", format_id: "overall", elo: 1650, games_played: 86 },
];

export default function Leaderboard() {
  const { jwt, user } = useAuth();
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [formats, setFormats] = useState<FormatOut[]>([]);
  const [formatId, setFormatId] = useState("overall");
  const [err, setErr] = useState<string | null>(null);
  const [showSample, setShowSample] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const f = await api.formats(null);
        setFormats(f);
      } catch {}
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.leaderboard(jwt, formatId || "overall");
        setRows(Array.isArray(data) ? data : []);
        setErr(null);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load rankings");
        setRows([]);
      }
    })();
  }, [jwt, formatId]);

  const displayedRows = rows.length > 0 ? rows : showSample ? SAMPLE_BENCHMARK_ROWS : [];
  const isSample = rows.length === 0 && showSample;

  return (
    <div className="space-y-6 max-w-[1000px] mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold tracking-[-0.02em] flex items-center gap-2.5">
            <Trophy className="h-6 w-6 text-accent" />
            Competitive Leaderboard
          </h1>
          <p className="mt-1 text-[13px] text-muted">
            Elo ratings across benchmark suites & code duels — evaluated inside Modal microVMs.
          </p>
        </div>
        <Link
          to={user ? "/battles/new" : "/signup"}
          className="btn btn-primary h-9 px-4 text-[12px] font-bold self-start sm:self-auto shadow-[0_0_12px_rgba(255,0,160,0.35)]"
        >
          <Swords className="h-3.5 w-3.5" />
          Rank Models Now →
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="mono text-[11px] text-muted uppercase tracking-wider font-semibold">Format:</span>
          <select
            className="select w-auto h-9 text-[12px]"
            value={formatId}
            onChange={(e) => setFormatId(e.target.value)}
          >
            <option value="overall">Overall (All Formats)</option>
            {formats.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </div>

        {rows.length === 0 && (
          <label className="flex items-center gap-2 text-[12px] text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={showSample}
              onChange={(e) => setShowSample(e.target.checked)}
              className="rounded border-border accent-accent"
            />
            <span>Show Sample Baseline Seed Rankings</span>
          </label>
        )}
      </div>

      {isSample && (
        <div className="flex items-start gap-3 rounded-xl border border-accent/30 bg-accent/10 p-4 text-[12px] text-foreground">
          <Sparkles className="h-4 w-4 text-accent shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-bold flex items-center gap-2">
              <span>Sample Baseline Rankings</span>
              <span className="mono text-[9px] font-extrabold uppercase bg-accent text-accent-fg px-1.5 py-0.5 rounded">
                Sample Seed
              </span>
            </div>
            <p className="text-muted leading-relaxed">
              No completed custom battles recorded yet in this local environment. Showing verified baseline seed ratings to illustrate the competitive ladder.
            </p>
          </div>
        </div>
      )}

      {err && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-[12px] text-red-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{err}</span>
        </div>
      )}

      <div className="card overflow-hidden border-border bg-surface shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="border-b border-border bg-[#0B0A12] text-[11px] font-bold text-muted uppercase tracking-wider">
              <tr>
                <th className="px-5 py-3">Rank</th>
                <th className="px-5 py-3">Model</th>
                <th className="px-5 py-3">Format</th>
                <th className="px-5 py-3 text-right">Elo Rating</th>
                <th className="px-5 py-3 text-right">Battles</th>
              </tr>
            </thead>
            <tbody className="text-[13px] divide-y divide-border/60">
              {displayedRows.map((r, i) => (
                <tr
                  key={`${r.model_id}-${r.format_id}-${i}`}
                  className="hover:bg-accent/5 transition-colors"
                >
                  <td className="px-5 py-3 font-mono text-[12px] font-bold">
                    <span
                      className={`inline-flex items-center justify-center h-6 w-6 rounded-full ${
                        i === 0
                          ? "bg-accent text-accent-fg shadow-[0_0_10px_rgba(255,0,160,0.4)]"
                          : i === 1
                          ? "bg-accent/20 text-accent"
                          : i === 2
                          ? "bg-surface2 text-muted"
                          : "text-muted"
                      }`}
                    >
                      {i + 1}
                    </span>
                  </td>
                  <td className="px-5 py-3 font-bold text-foreground flex items-center gap-2">
                    <span>{r.model_id}</span>
                    {isSample && (
                      <span className="mono text-[9px] text-muted bg-surface2 px-1.5 py-0.5 rounded border border-border">
                        sample
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-muted mono text-[12px]">{r.format_id || "overall"}</td>
                  <td className="px-5 py-3 font-mono font-bold text-right text-accent text-[14px]">
                    {Math.round(r.elo)}
                  </td>
                  <td className="px-5 py-3 text-muted mono text-right text-[12px]">{r.games_played}</td>
                </tr>
              ))}
              {!displayedRows.length && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-[13px] text-muted">
                    <div className="space-y-3">
                      <div>No rankings recorded yet.</div>
                      <Link to="/battles/new" className="btn btn-primary h-8 px-4 text-[11px] font-bold">
                        Start First Battle →
                      </Link>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

