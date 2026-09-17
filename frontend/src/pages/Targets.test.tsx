import type { AnchorHTMLAttributes, ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ChallengeSectionTabs } from "./Targets";

vi.mock("react-router-dom", () => ({
  Link: ({ to, children, ...props }: { to: string; children?: ReactNode } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">) =>
    <a href={to} {...props}>{children}</a>,
  useSearchParams: () => [new URLSearchParams()],
}));

describe("challenge section tabs", () => {
  it("links the Official and User catalogs as separate pages", () => {
    const html = renderToStaticMarkup(
      <ChallengeSectionTabs section="official" />,
    );

    expect(html).toContain('href="/challenges/official"');
    expect(html).toContain('href="/challenges/user"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain("Official");
    expect(html).toContain("User");
  });
});
