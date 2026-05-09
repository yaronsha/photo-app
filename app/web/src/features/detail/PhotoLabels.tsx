interface PhotoLabelsProps {
  tags?: string[];
  activities?: string[];
  subjectType?: string | null;
  primaryFocus?: string | null;
  settingType?: string | null;
  indoorOutdoor?: string | null;
  sharpness?: string | null;
  faceClarityScore?: number | null;
  contentType?: string | null;
}

function sharpnessColor(v: string): string {
  if (v === 'sharp') return 'bg-green-100 text-green-800';
  if (v === 'very_blurry') return 'bg-red-100 text-red-800';
  return 'bg-amber-100 text-amber-800';
}

function faceColor(score: number): string {
  if (score >= 4) return 'bg-green-100 text-green-800';
  if (score === 3) return 'bg-amber-100 text-amber-800';
  return 'bg-red-100 text-red-800';
}

export function PhotoLabels({
  tags,
  activities,
  subjectType,
  primaryFocus,
  settingType,
  indoorOutdoor,
  sharpness,
  faceClarityScore,
  contentType,
}: PhotoLabelsProps) {
  const standardLabels: string[] = [
    ...(tags ?? []),
    ...(activities ?? []),
  ];

  const analysisChips: { label: string; value: string; colorClass: string }[] = [];

  if (subjectType) {
    analysisChips.push({ label: 'subject', value: subjectType.replace(/_/g, ' '), colorClass: 'bg-secondary-container text-on-secondary-container' });
  }
  if (primaryFocus) {
    analysisChips.push({ label: 'focus', value: primaryFocus.replace(/_/g, ' '), colorClass: 'bg-secondary-container text-on-secondary-container' });
  }
  if (settingType) {
    analysisChips.push({ label: 'setting', value: settingType.replace(/_/g, ' '), colorClass: 'bg-secondary-container text-on-secondary-container' });
  }
  if (indoorOutdoor) {
    analysisChips.push({ label: 'in/out', value: indoorOutdoor.replace(/_/g, ' '), colorClass: 'bg-secondary-container text-on-secondary-container' });
  }
  if (sharpness) {
    analysisChips.push({
      label: 'sharpness',
      value: sharpness.replace(/_/g, ' '),
      colorClass: sharpnessColor(sharpness),
    });
  }
  if (faceClarityScore != null) {
    const score = Number(faceClarityScore);
    analysisChips.push({
      label: 'face',
      value: '●'.repeat(score) + '○'.repeat(5 - score) + ' ' + score,
      colorClass: faceColor(score),
    });
  }
  if (contentType && contentType !== 'photo') {
    analysisChips.push({ label: 'type', value: contentType, colorClass: 'bg-amber-100 text-amber-800' });
  }

  if (!standardLabels.length && !analysisChips.length) return null;

  return (
    <div className="space-y-sm">
      <h4 className="text-label-md text-on-surface-variant uppercase tracking-wider">Labels</h4>
      <div className="flex flex-wrap gap-xs">
        {standardLabels.map(l => (
          <span
            key={l}
            className="px-sm py-xs bg-secondary-container text-on-secondary-container text-label-md font-medium rounded-full"
          >
            {l}
          </span>
        ))}
        {analysisChips.map(chip => (
          <span
            key={chip.label}
            title={chip.label}
            className={`px-sm py-xs text-label-md font-medium rounded-full ${chip.colorClass}`}
          >
            {chip.value}
          </span>
        ))}
      </div>
    </div>
  );
}
