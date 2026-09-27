import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { helpArticleByPath, helpArticles, helpCategories, helpSearch } from './helpContent';
import { helpWalkthroughs } from './help';
import { helpStepCaptures } from './help/visuals';
import { helpSeoRoutes } from './helpSeo';
import { pageForPath } from './workspaceRoutes';
import { seoPage } from './seo';

describe('Detailed Help Center content contract', () => {
  it('retains every existing guide and indexes every expanded guide', () => {
    const original = readFileSync(new URL('./helpContent.ts', import.meta.url), 'utf8');
    const paths = [...original.matchAll(/article\("(\/help[^"]+)"/g)].map(match => match[1]);
    expect(paths.length).toBeGreaterThanOrEqual(51);
    for (const path of paths) expect(helpArticleByPath.has(path), path).toBe(true);
    expect(helpArticles.length).toBe(Object.keys(helpWalkthroughs).length);
    expect(new Set(helpArticles.map(item => item.path)).size).toBe(helpArticles.length);
  });
  it('keeps categories, real app routes, and crawler metadata in sync', () => {
    const reachable = new Set(helpCategories.flatMap(category => category.articles));
    for (const article of helpArticles) {
      expect(reachable.has(article.path), article.path).toBe(true);
      expect(pageForPath(helpWalkthroughs[article.path].appPath), article.path).not.toBeNull();
      expect(helpSeoRoutes[article.path].description).toBe(article.summary);
      expect(helpSeoRoutes[article.path].title).toBe(`${article.title} | DoobieLogic Help`);
      expect(seoPage(true, article.path)).toMatchObject({publicPage:true,canonical:`https://doobielogic.io${article.path}`});
    }
    for (const path of reachable) expect(helpArticleByPath.has(path), path).toBe(true);
  });
  it('gives each action instructions, a checkable outcome, and verified source paths', () => {
    for (const [path, guide] of Object.entries(helpWalkthroughs)) {
      expect(guide.beforeYouStart.length, path).toBeGreaterThan(0);
      expect(guide.steps.length, path).toBeGreaterThanOrEqual(3);
      expect(guide.completion.length, path).toBeGreaterThan(0);
      expect(guide.troubleshooting.length, path).toBeGreaterThan(0);
      expect(new Set(guide.steps.map(step => step.id)).size, path).toBe(guide.steps.length);
      expect(guide.sourceFiles.length, path).toBeGreaterThan(0);
      for (const file of guide.sourceFiles) expect(existsSync(new URL(`../../../${file}`, import.meta.url)), `${path}: ${file}`).toBe(true);
      for (const step of guide.steps) {
        expect(step.id, path).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
        expect(step.instructions.length, `${path}: ${step.id}`).toBeGreaterThan(0);
        expect(step.expected.length, `${path}: ${step.id}`).toBeGreaterThan(20);
        for (const field of step.fields ?? []) {
          expect(field.label.trim()).not.toBe('');
          expect(field.requirement.trim()).not.toBe('');
          expect(field.guidance.length).toBeGreaterThan(15);
        }
      }
      expect(JSON.stringify(guide), path).not.toMatch(/[\u2014]/);
    }
  });
  it('attaches real capture evidence to existing step IDs, never array positions', () => {
    for (const [path, steps] of Object.entries(helpStepCaptures)) {
      expect(helpWalkthroughs[path], path).toBeDefined();
      for (const [id, captures] of Object.entries(steps)) {
        expect(helpWalkthroughs[path].steps.some(step => step.id === id), `${path}: ${id}`).toBe(true);
        for (const capture of captures) {
          expect(capture.releaseSha).toMatch(/^[a-f0-9]{40}$/);
          expect(capture.alt.length).toBeGreaterThan(10);
          expect(capture.caption.length).toBeGreaterThan(10);
          expect(Number.isNaN(Date.parse(capture.capturedAt))).toBe(false);
          expect(capture.src).toMatch(/^\/help\/screens\/[a-z0-9-]+\.webp$/);
          const file = new URL(`../../public${capture.src}`, import.meta.url);
          expect(existsSync(file), capture.src).toBe(true);
          expect(readFileSync(file).length).toBeGreaterThan(1000);
        }
      }
    }
  });
  it('searches the expanded field guidance and instructions', () => {
    expect(helpSearch('receive inventory').some(item => item.path === '/help/inventory/receiving')).toBe(true);
    expect(helpSearch('Metrc').some(item => item.path === '/help/settings/integrations')).toBe(true);
    expect(helpSearch('password').some(item => item.path === '/help/settings/admin')).toBe(true);
    expect(helpSearch('mapping').some(item => item.category === 'cultivation')).toBe(true);
  });
});
