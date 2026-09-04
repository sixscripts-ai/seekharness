import { CheckCircle2, CircleAlert, CircleDot, CircleSlash2, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  status: string;
  verificationStatus?: string | null;
  compact?: boolean;
};

export default function BattleStatus({ status, verificationStatus, compact = false }: Props) {
  const normalized = String(status || "queued").toLowerCase();
  const verification = String(verificationStatus || "").toLowerCase();

  let label = normalized;
  let Icon = CircleDot;
  let tone = "text-zinc-400";

  if (normalized === "running" || normalized === "queued") {
    label = normalized === "running" ? "Live" : "Queued";
    Icon = normalized === "running" ? Loader2 : CircleDot;
    tone = normalized === "running" ? "text-cyan-400 drop-shadow-[0_0_8px_rgba(0,210,255,0.6)]" : "text-zinc-400";
  } else if (normalized === "completed" && verification === "verified_pass") {
    label = "Verified pass";
    Icon = CheckCircle2;
    tone = "text-emerald-300";
  } else if (normalized === "completed" && verification === "verified_fail") {
    label = "Verified fail";
    Icon = XCircle;
    tone = "text-rose-300";
  } else if (normalized === "completed" && verification === "infra_failure") {
    label = "Infrastructure failure";
    Icon = CircleAlert;
    tone = "text-amber-300";
  } else if (normalized === "completed") {
    label = verification === "not_attempted" ? "Unverified" : "Completed";
    Icon = CheckCircle2;
    tone = verification === "not_attempted" ? "text-amber-300" : "text-zinc-300";
  } else if (normalized === "failed") {
    label = "Failed";
    Icon = XCircle;
    tone = "text-rose-300";
  } else if (normalized === "cancelled") {
    label = "Cancelled";
    Icon = CircleSlash2;
    tone = "text-zinc-500";
  }

  return (
    <span className={cn("inline-flex items-center gap-1.5 font-mono font-semibold", compact ? "text-[10px]" : "text-[11px]", tone)}>
      <Icon className={cn("h-3.5 w-3.5", normalized === "running" && "animate-spin")} />
      <span>{label}</span>
    </span>
  );
}
