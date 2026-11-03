import { useEffect, useState } from "react";
import { delegationApi, teamApi, type CaseOverview, type ResumeBriefing, type TeamOverview } from "../api";

type Tone = "ok" | "warn" | "error" | "neutral";
type Tile = { label: string; value: string | number; tone: Tone; hint: string };

// A read-only forensic situation board: the states that decide whether a case
// is actually ready — what is verified, what is only claimed, what is still
// open, what is about to be lost, and where the team disagrees — surfaced as
// first-class elements instead of small badges buried in the scroll. Colour
// only reinforces the number and label; it never carries meaning on its own.
export function SituationStrip({
  caseId,
  caseVersion,
  overview,
}: {
  caseId: string;
  caseVersion: number;
  overview: CaseOverview;
}) {
  const [team, setTeam] = useState<TeamOverview | null>(null);
  const [resume, setResume] = useState<ResumeBriefing | null>(null);

  useEffect(() => {
    teamApi.overview(caseId).then(setTeam, () => setTeam(null));
    delegationApi.resume(caseId).then(setResume, () => setResume(null));
  }, [caseId, caseVersion]);

  const reqs = team?.requirements ?? [];
  const verified = overview.evidence.filter((e) => e.independently_verified).length;
  const claimed = reqs.filter(
    (r) => r.requirement.responsibility.status === "reported_done" && !r.requirement.resolved,
  ).length;
  const open = reqs.filter((r) => !r.requirement.resolved && !r.requirement.unresolvable).length;
  const conflicts = reqs.filter((r) => r.open_conflicts.length > 0).length;
  const atRisk = resume?.recovery_still_open.length ?? 0;
  const revoked = Boolean(overview.mandate.revoked);

  const tiles: Tile[] = [
    { label: "Verified", value: verified, tone: "ok", hint: "evidence independently verified" },
    {
      label: "Claimed, not verified",
      value: claimed,
      tone: claimed > 0 ? "warn" : "neutral",
      hint: "reported done, with no independent check — the coordination gap this tool exists to close",
    },
    { label: "Open", value: open, tone: "neutral", hint: "requirements still open" },
    {
      label: "At risk",
      value: atRisk,
      tone: atRisk > 0 ? "warn" : "neutral",
      hint: "recovery windows still open — recoverable, for now",
    },
    {
      label: "Unresolved conflict",
      value: conflicts,
      tone: conflicts > 0 ? "error" : "neutral",
      hint: "team members disagree on a requirement; surfaced loudly, never overwritten",
    },
    {
      label: "Authority",
      value: revoked ? "Revoked" : "Active",
      tone: revoked ? "error" : "ok",
      hint: revoked ? "the case mandate has been revoked" : "the case mandate is in force",
    },
  ];

  return (
    <section className="situation-strip" aria-label="Case situation at a glance">
      {tiles.map((t) => (
        <div key={t.label} className={`situation-tile tone-${t.tone}`} title={t.hint}>
          <div className="situation-value">{t.value}</div>
          <div className="situation-label">{t.label}</div>
        </div>
      ))}
    </section>
  );
}
