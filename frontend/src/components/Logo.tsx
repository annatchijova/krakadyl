// A compact K / crocodile-profile mark, per the brand direction: small
// eye, horizontal snout, simple geometry so it still reads at 24px in
// one color. A study, not a finished logo file.
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--panel-raised)" stroke="var(--border)" />
      <path
        d="M9 7 L9 25 M9 16 L17 7 M9 16 L19 25"
        stroke="var(--signal)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="24" cy="11" r="1.4" fill="var(--signal)" />
      <path
        d="M20 14 L27 16 L20 18 Z"
        fill="none"
        stroke="var(--signal)"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}
