import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { HelpWalkthrough } from './HelpWalkthrough';
import { retailWalkthroughs } from '../lib/help/retail';

describe('Detailed walkthrough presentation', () => {
  const path = '/help/inventory/receiving';
  const guide = retailWalkthroughs[path];
  it('renders field guidance, stable navigation, and an outcome for every step', () => {
    const html = renderToStaticMarkup(<HelpWalkthrough path={path} guide={guide}/>);
    expect(html).toContain('Before you start');
    expect(html).toContain('What to enter or choose');
    expect(html).toContain('METRC quantity');
    expect(html).toContain('Provider-controlled');
    expect(html).toContain('id="receiving-open-queue"');
    expect(html).toContain('href="#receiving-open-queue"');
    expect(html.match(/What you should see/g)?.length).toBe(guide.steps.length);
    expect(html).toContain('Check your work');
    expect(html).toContain('Something not working?');
  });
  it('labels reference images and provides an accessible enlarge control', () => {
    const html = renderToStaticMarkup(<HelpWalkthrough path={path} guide={guide}/>);
    expect(html).toContain('Enlarge screenshot:');
    expect(html).toContain('Close enlarged screenshot');
    expect(html).toContain('Captured September 26, 2026.');
  });
});
