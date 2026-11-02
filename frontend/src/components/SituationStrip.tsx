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
    { label: "Verificado", value: verified, tone: "ok", hint: "evidencia verificada de forma independiente" },
    {
      label: "Declarado, sin verificar",
      value: claimed,
      tone: claimed > 0 ? "warn" : "neutral",
      hint: "reportado como hecho, sin verificación independiente — el agujero de coordinación que esta herramienta existe para cerrar",
    },
    { label: "Abierto", value: open, tone: "neutral", hint: "requisitos todavía abiertos" },
    {
      label: "En riesgo",
      value: atRisk,
      tone: atRisk > 0 ? "warn" : "neutral",
      hint: "ventanas de recuperación todavía abiertas — recuperable, por ahora",
    },
    {
      label: "Conflicto sin resolver",
      value: conflicts,
      tone: conflicts > 0 ? "error" : "neutral",
      hint: "el equipo está en desacuerdo sobre un requisito; se muestra con claridad, nunca se sobrescribe",
    },
    {
      label: "Autoridad",
      value: revoked ? "Revocada" : "Activa",
      tone: revoked ? "error" : "ok",
      hint: revoked ? "el mandato del caso fue revocado" : "el mandato del caso está vigente",
    },
  ];

  return (
    <section className="situation-strip" aria-label="Situación del caso de un vistazo">
      {tiles.map((t) => (
        <div key={t.label} className={`situation-tile tone-${t.tone}`} title={t.hint}>
          <div className={`situation-value${t.tone === "neutral" && t.value === 0 ? " quiet" : ""}`}>{t.value}</div>
          <div className="situation-label">{t.label}</div>
        </div>
      ))}
    </section>
  );
}
