import type { ActivityEvent } from "../api";

export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <section className="panel">
      <h2>Activity</h2>
      <div className="activity-list">
        {[...events].reverse().map((e, i) => (
          <div key={i} className="activity-item">
            <div className="ts mono">
              {new Date(e.ts).toLocaleTimeString()} · {e.kind}
            </div>
            <div>{e.summary}</div>
          </div>
        ))}
        {events.length === 0 && <p className="reason-text">No activity yet.</p>}
      </div>
    </section>
  );
}
