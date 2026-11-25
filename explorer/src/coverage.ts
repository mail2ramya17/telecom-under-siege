import { AttackPath, Control, PathCoverage, SEVERITY_WEIGHT } from './model';

/** Compute which controls cover each step of each attack path. */
export function analyze(paths: AttackPath[], controls: Control[]): PathCoverage[] {
  return paths.map((path) => {
    const steps = path.steps.map((step) => ({
      step,
      controls: controls.filter((c) => c.mitigates.includes(step.id)),
    }));
    const coveredSteps = steps.filter((s) => s.controls.length > 0).length;
    const coverage = coveredSteps / path.steps.length;
    const residualRisk = round1(SEVERITY_WEIGHT[path.severity] * (1 - coverage));
    // A chain is breakable if any step before the final impact step is covered.
    const chainBreakable = steps.slice(0, -1).some((s) => s.controls.length > 0);
    return { path, steps, coveredSteps, coverage, residualRisk, chainBreakable };
  });
}

/** Controls that do not map to any known step: usually a data-entry mistake. */
export function orphanControls(paths: AttackPath[], controls: Control[]): Control[] {
  const ids = new Set(paths.flatMap((p) => p.steps.map((s) => s.id)));
  return controls.filter((c) => c.mitigates.some((m) => !ids.has(m)));
}

export function toMarkdown(results: PathCoverage[], disabled: string[]): string {
  const out: string[] = [];
  out.push('# Telecom attack-path coverage report', '');
  if (disabled.length) out.push(`> Simulating missing controls: ${disabled.join(', ')}`, '');
  out.push('| Attack path | Severity | Steps covered | Coverage | Residual risk (0-10) | Chain breakable |');
  out.push('|---|---|---|---|---|---|');
  for (const r of results) {
    out.push(
      `| ${r.path.name} | ${r.path.severity} | ${r.coveredSteps}/${r.path.steps.length} | ` +
        `${Math.round(r.coverage * 100)}% | ${r.residualRisk} | ${r.chainBreakable ? 'yes' : '**NO**'} |`,
    );
  }
  for (const r of results) {
    out.push('', `## ${r.path.name}`, '', `Impact: ${r.path.impact}`, '');
    r.steps.forEach((s, i) => {
      const ctl = s.controls.length ? s.controls.map((c) => c.name).join('; ') : '**GAP: no control**';
      out.push(`${i + 1}. ${s.step.label} \`${s.step.technique}\` -> ${ctl}`);
    });
  }
  return out.join('\n');
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}
