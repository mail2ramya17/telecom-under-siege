/**
 * Domain model for the telecom attack-path explorer.
 * Attack paths are ordered kill chains; controls mitigate individual steps.
 */

export type Severity = 'low' | 'medium' | 'high' | 'critical';

export type Layer = 'minimize' | 'identity' | 'network' | 'pipeline' | 'ai-guard' | 'detect';

export interface Step {
  /** Unique step id, e.g. "sim.port" */
  id: string;
  label: string;
  /** MITRE ATT&CK / ATLAS technique id, or a short framework reference */
  technique: string;
}

export interface AttackPath {
  id: string;
  name: string;
  impact: string;
  severity: Severity;
  steps: Step[];
}

export interface Control {
  id: string;
  name: string;
  layer: Layer;
  /** Step ids this control prevents or detects */
  mitigates: string[];
  tools: string[];
}

export interface StepCoverage {
  step: Step;
  controls: Control[];
}

export interface PathCoverage {
  path: AttackPath;
  steps: StepCoverage[];
  coveredSteps: number;
  coverage: number; // 0..1
  /** severity weight x share of uncovered steps, 0..10 */
  residualRisk: number;
  /** true when at least one step can break the chain before impact */
  chainBreakable: boolean;
}

export const SEVERITY_WEIGHT: Record<Severity, number> = {
  low: 2.5,
  medium: 5,
  high: 7.5,
  critical: 10,
};
