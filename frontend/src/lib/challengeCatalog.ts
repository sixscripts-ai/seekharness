import type { BattleDraftOut, BattleTemplate, FormatOut, TargetSummaryOut } from "./api";
import { isCustomFormat } from "./api";
import { formatScoring } from "./challengeNavigation";

export type ChallengeSection = "official" | "user" | "all";

export type ChallengeEntry = {
  key: string;
  title: string;
  description: string;
  kind: "Built-in" | "Template" | "Saved";
  meta: string[];
  href: string;
  detail?: string;
};

type ChallengeCatalogInput = {
  targets: TargetSummaryOut[];
  formats: FormatOut[];
  templates: BattleTemplate[];
  drafts: BattleDraftOut[];
};

export function challengeCatalogPath(section: Exclude<ChallengeSection, "all">): string {
  return `/challenges/${section}`;
}

export function buildChallengeCatalog(
  section: ChallengeSection,
  { targets, formats, templates, drafts }: ChallengeCatalogInput,
): ChallengeEntry[] {
  const official: ChallengeEntry[] = [
    ...targets.map(target => ({
      key: `target:${target.id}`,
      title: target.name,
      description: target.description,
      kind: "Built-in" as const,
      meta: [
        target.format === "builder_breaker" ? "Builder vs. Breaker" : "Solo or head-to-head",
        target.runtime,
        target.difficulty,
      ],
      href: `/battles/new?target=${encodeURIComponent(target.id)}`,
      detail: `/challenges/${encodeURIComponent(target.id)}`,
    })),
    ...formats.filter(format => !isCustomFormat(format)).map(format => ({
      key: `format:${format.id}`,
      title: format.name,
      description: format.description || "A platform challenge with its own roles and execution rules.",
      kind: "Template" as const,
      meta: [formatScoring(format)],
      href: `/battles/new?format=${encodeURIComponent(format.id)}`,
    })),
    ...templates.map(template => ({
      key: `template:${template.id}`,
      title: template.title,
      description: template.brief,
      kind: "Template" as const,
      meta: [template.category, template.mode === "verified" ? "Test-scored" : "Judge-scored"],
      href: `/battles/new?custom=1&template=${encodeURIComponent(template.id)}`,
    })),
  ];

  const user: ChallengeEntry[] = drafts.map(draft => ({
    key: `draft:${draft.id}`,
    title: draft.spec.title || "Untitled challenge",
    description: draft.spec.brief || "Continue editing your custom challenge.",
    kind: "Saved" as const,
    meta: [
      draft.mode === "verified" ? "Test-scored" : "Judge-scored",
      draft.status === "launched" ? "Reusable challenge" : draft.status,
    ],
    href: `/battles/new?custom=1&draft=${encodeURIComponent(draft.id)}`,
  }));

  if (section === "official") return official;
  if (section === "user") return user;
  return [...official, ...user];
}
