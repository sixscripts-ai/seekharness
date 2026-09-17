import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import BattleSetupActions from "./BattleSetupActions";

describe("explicit battle launch", () => {
  it.each([false, true])("never makes setup actions implicit submit buttons (review=%s)", review => {
    const html = renderToStaticMarkup(<BattleSetupActions review={review} disabled={false} busy={false} onBack={() => {}} onReview={() => {}} onStart={() => {}} />);
    expect(html.match(/type="button"/g)).toHaveLength(2);
    expect(html).not.toContain('type="submit"');
    expect(html).toContain(review ? "Start battle" : "Review battle");
  });
  it("review prevents the default action and does not invoke launch", () => {
    const onStart = vi.fn();
    const onReview = vi.fn();
    const preventDefault = vi.fn();
    const tree = BattleSetupActions({ review: false, disabled: false, busy: false, onBack: vi.fn(), onStart, onReview });
    const primary = tree.props.children.filter(Boolean).find((child: { props?: { className?: string } }) => child.props?.className === "btn btn-primary");
    primary.props.onClick({ preventDefault });
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(onReview).toHaveBeenCalledOnce();
    expect(onStart).not.toHaveBeenCalled();
  });
});
