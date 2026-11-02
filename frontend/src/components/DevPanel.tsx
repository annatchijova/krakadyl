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
      <h2>Simular (solo dev)</h2>
      <p className="reason-text" style={{ marginTop: 0 }}>
        Estas mutan el caso para demostrar la detección de obsolescencia — nunca una acción investigativa real.
      </p>
      <div className="buttons">
        <button className="button-secondary" onClick={onTamper} disabled={busy}>
          Alterar el archivo de obs-a1
        </button>
        <button className="button-secondary" onClick={onRevokeMandate} disabled={busy}>
          Revocar el mandato
        </button>
        <button className="button-secondary" onClick={onUnresolveHypothesis} disabled={busy}>
          Marcar el requisito de timestamp como irresoluble
        </button>
        <button className="button-danger" onClick={onReset} disabled={busy}>
          Reiniciar caso
        </button>
      </div>
    </div>
  );
}
