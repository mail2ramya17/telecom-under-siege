/**
 * Usage:
 *   node dist/cli.js                         # full coverage report (Markdown)
 *   node dist/cli.js --disable net-sigfw     # what if the signaling firewall is missing?
 *   node dist/cli.js --json                  # machine-readable output
 *   node dist/cli.js --fail-under 60         # exit 1 if any path is below 60% coverage (CI gate)
 */
import { ATTACK_PATHS, CONTROLS } from './data';
import { analyze, orphanControls, toMarkdown } from './coverage';

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

const disabled = (arg('--disable') ?? '').split(',').filter(Boolean);
const unknown = disabled.filter((d) => !CONTROLS.some((c) => c.id === d));
if (unknown.length) {
  console.error(`Unknown control id(s): ${unknown.join(', ')}`);
  console.error(`Known: ${CONTROLS.map((c) => c.id).join(', ')}`);
  process.exit(2);
}

const orphans = orphanControls(ATTACK_PATHS, CONTROLS);
if (orphans.length) {
  console.error(`Controls mapped to unknown steps: ${orphans.map((c) => c.id).join(', ')}`);
  process.exit(2);
}

const active = CONTROLS.filter((c) => !disabled.includes(c.id));
const results = analyze(ATTACK_PATHS, active);

if (process.argv.includes('--json')) {
  console.log(
    JSON.stringify(
      results.map((r) => ({
        path: r.path.id,
        coverage: r.coverage,
        residualRisk: r.residualRisk,
        chainBreakable: r.chainBreakable,
        gaps: r.steps.filter((s) => !s.controls.length).map((s) => s.step.id),
      })),
      null,
      2,
    ),
  );
} else {
  console.log(toMarkdown(results, disabled));
}

const failUnder = arg('--fail-under');
if (failUnder !== undefined) {
  const threshold = Number(failUnder) / 100;
  const failing = results.filter((r) => r.coverage < threshold);
  if (failing.length) {
    console.error(`Coverage below ${failUnder}%: ${failing.map((r) => r.path.id).join(', ')}`);
    process.exitCode = 1;
  }
}
