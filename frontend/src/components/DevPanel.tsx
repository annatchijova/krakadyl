// Clearly separated from the real investigative actions (dashed
// border, distinct heading color) — these exist to demonstrate Level
// 2's staleness/recovery mechanism, not as something an investigator
// would ever click on a real case.
export function DevPanel({
  busy,
  onTamper,
  onRevokeMandate,
  onUnresolveHypothesis,
  onReset,
}: {
  busy: boolean;
  onTamper: () => void;
  onRevokeMandate: () => void;
  onUnresolveHypothesis: () => void;
  onReset: () => void;
}) {
  return (
    <div className="dev-panel">
      <h2>Simulate (dev only)</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        These mutate the case to demonstrate staleness detection — never a real investigative action.
      </p>
      <div className="buttons">
        <button className="button-secondary" onClick={onTamper} disabled={busy}>
          Tamper obs-a1's file
        </button>
        <button className="button-secondary" onClick={onRevokeMandate} disabled={busy}>
          Revoke the mandate
        </button>
        <button className="button-secondary" onClick={onUnresolveHypothesis} disabled={busy}>
          Make timestamp requirement unresolvable
        </button>
        <button className="button-danger" onClick={onReset} disabled={busy}>
          Reset case
        </button>
      </div>
    </div>
  );
}
