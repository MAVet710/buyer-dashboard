import { retailWalkthroughs } from './retail';
import { productionWalkthroughs } from './production';
import { cultivationWalkthroughs } from './cultivation';
import { wholesaleWalkthroughs } from './wholesale';
import { operationsWalkthroughs } from './operations';
import { complianceWalkthroughs } from './compliance';
import type { HelpWalkthroughRegistry } from './types';

export const HELP_REVIEWED_RELEASE = 'fd91e4f7991e3d65f7adb81cd0765f0d9e3395bc';
export const helpWalkthroughs: HelpWalkthroughRegistry = {
  ...retailWalkthroughs, ...productionWalkthroughs, ...cultivationWalkthroughs,
  ...wholesaleWalkthroughs, ...operationsWalkthroughs, ...complianceWalkthroughs,
};
export const helpWalkthroughByPath = new Map(Object.entries(helpWalkthroughs));
export function walkthroughSearchText(path: string): string {
  const guide = helpWalkthroughByPath.get(path);
  if (!guide) return '';
  return [guide.title, guide.summary, guide.navPath, ...guide.beforeYouStart,
    ...guide.steps.flatMap(step => [step.title, ...step.instructions, step.expected,
      step.warning ?? '', ...(step.fields ?? []).flatMap(field => [field.label,
        field.requirement, field.guidance, field.example ?? ''])]),
    ...guide.completion, ...guide.troubleshooting.flatMap(item => [item.symptom, item.resolution]),
  ].join(' ');
}
