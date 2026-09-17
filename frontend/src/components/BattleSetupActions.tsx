export default function BattleSetupActions({ review, disabled, busy, onBack, onReview, onStart }: {
  review: boolean;
  disabled: boolean;
  busy: boolean;
  onBack: () => void;
  onReview: () => void;
  onStart: () => void;
}) {
  return <div className="mt-8 flex items-center justify-between gap-4 border-t border-white/10 pt-6">
    <button type="button" disabled={busy} className="btn btn-ghost" onClick={onBack}>
      {review ? "Back to models" : "Back to challenges"}
    </button>
    {/* Both stages are explicit actions. Changing a button from type=button
        to type=submit during a click can submit the newly rendered review. */}
    <button type="button" className="btn btn-primary" disabled={disabled}
      onClick={event => { event.preventDefault(); if (review) onStart(); else onReview(); }}>
      {busy ? "Starting…" : review ? "Start battle" : "Review battle"}
    </button>
  </div>;
}
