import type { Stage } from "./cultivationIntelligenceTypes";

/** API responses contain immutable IDs and derived fields, never draft inputs. */
export function recipeDraftPayload(name: string, description: string, stages: Stage[]) {
  return {
    name,
    description,
    stages: stages.map((stage, sequence) => ({
      stage_key: stage.stage_key,
      display_name: stage.display_name,
      sequence,
      targets: stage.targets.map(target => ({
        metric: target.metric,
        minimum: target.minimum,
        maximum: target.maximum,
        unit: target.unit,
        threshold_seconds: target.threshold_seconds ?? null,
      })),
    })),
  };
}
