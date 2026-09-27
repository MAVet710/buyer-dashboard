export type HelpField = {
  label: string;
  requirement: string;
  guidance: string;
  example?: string;
};
export type HelpStep = {
  id: string;
  title: string;
  instructions: string[];
  fields?: HelpField[];
  expected: string;
  warning?: string;
};
export type HelpTroubleshooting = { symptom: string; resolution: string };
export type HelpWalkthrough = {
  title: string;
  category: string;
  summary: string;
  navPath: string;
  appPath: string;
  beforeYouStart: string[];
  steps: HelpStep[];
  completion: string[];
  troubleshooting: HelpTroubleshooting[];
  sourceFiles: string[];
};
export type HelpWalkthroughRegistry = Record<string, HelpWalkthrough>;
