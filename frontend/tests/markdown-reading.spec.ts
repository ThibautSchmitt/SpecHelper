import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';

const id = '71717171-7171-4171-8171-717171717171';
const ticket = '72727272-7272-4272-8272-727272727272';
const at = '2026-11-04T10:00:00Z';
const queryId = `sql-${'a'.repeat(32)}-${'b'.repeat(12)}`;
const sql = "SELECT playlist_id, count(*) AS tracks\nFROM playlist_track\nWHERE active = true\nGROUP BY playlist_id;";
const body = `## Besoin\n\nCorriger le **calcul** des cotisations.\n\n## Critères d’acceptation\n\n- [ ] Inclure les ajustements.\n- Préserver les dossiers archivés.\n\n| Cas | Résultat |\n| --- | ---: |\n| Dossier actif | 42 |\n\n> Une précision reste à vérifier.\n\n\`\`\`sql\n${sql}\n\`\`\``;
const documentMarkdown = `## Procédure\n\nUne **règle métier** documentée.\n\n- Contrôler les dates.\n- Conserver les références.\n\n| État | Action |\n| --- | --- |\n| Actif | Vérifier |\n\n[Documentation](https://example.org/docs)\n\n![Ne pas charger](https://reader-remote.invalid/tracker.png)\n\n<script>window.readerInjected=true</script>\n\n[Interdit](javascript:alert(1))`;

async function setup(page: Page, language: 'en' | 'fr', theme: string) {
  let draft = { id: ticket, active: true, revision: 1, discussion_revision: 2, source_version: null,
    source_verified: false, title: 'Corriger le calcul', body, markdown: body, scope_choice: 'unknown', proposal: null, generation: null };
  const value = { id, title: 'Calcul des cotisations', need: 'Comprendre les cotisations', workflow: 'question',
    environment_id: 1, environment_name: 'Recette', status: 'DISCUSSING', conversation_state: 'DISCUSSION',
    created_at: at, analysis_protocol: '2.4', baseline: [], database: {}, attachments: [], progress: [], error: '',
    questions: [], conversation: [], latest_version: null, versions: [], decisions: [], decision_history: [], decision_revision: 0,
    analysis_runs: [], publications: [], conversation_tickets: [], work_progress: [],
    active_ticket: { id: ticket, title: draft.title, status: 'DRAFT' },
    discussion: { enabled: true, mode: 'discussion', revision: 2, job: null },
    messages: [{ id: 1, role: 'user', kind: 'discussion', content: 'Comment calculer les cotisations ?', created_at: at },
      { id: 2, role: 'assistant', kind: 'discussion_reply', content: `Résultat observé. Source : \`${queryId}\`.`, created_at: at,
        data: { observations: { database_checks: [{ query_id: queryId, sql, status: 'checked', row_count: 1 }] } } }],
  };
  let reads = 0;
  const writes: unknown[] = [];
  const remote: string[] = [];
  await page.addInitScript(value => localStorage.setItem('spechelper-theme', value), theme);
  page.on('request', r => { if (r.url().startsWith('https://reader-remote.invalid')) remote.push(r.url()); });
  await page.route('https://reader-remote.invalid/**', r => r.abort());
  await page.route('**/api/**', r => {
    if (r.request().method() !== 'GET') throw new Error('Unexpected write: ' + r.request().url());
    return r.fulfill({ json: [] });
  });
  await page.route('**/api/access/session', r => r.fulfill({ json: { authenticated: true, mode: 'local' } }));
  await page.route('**/api/settings', r => r.fulfill({ json: { name: 'SpecHelper', language } }));
  await page.route(`**/api/analyses/${id}`, r => r.fulfill({ json: value }));
  await page.route(new RegExp(`/api/analyses/${id}/ticket-preparation(?:\\?.*)?$`), r => {
    if (r.request().method() === 'PUT') {
      const payload = r.request().postDataJSON(); writes.push(payload);
      draft = { ...draft, ...payload, revision: draft.revision + 1, markdown: payload.body };
    }
    return r.fulfill({ json: draft });
  });
  await page.route(`**/api/analyses/${id}/messages/2/sources`, r => {
    reads++;
    return r.fulfill({ json: { sources: [
      { id: queryId, kind: 'sql', sql, status: 'checked', row_count: 1 },
      { id: 'code', kind: 'git', title: 'benefits/calculate.py', repository: 'example/project', commit: 'a'.repeat(40),
        excerpt: 'def calculate(amount):\n    return amount + 42\n# <script>window.readerInjected=true</script>' },
      { id: 'document', kind: 'document', title: 'procedure.md', version: 1, excerpt: documentMarkdown },
      { id: 'web', kind: 'web', title: 'Documentation publique', url: 'https://example.org/reference', excerpt: documentMarkdown },
      { id: 'unknown', kind: 'git', title: 'sample.unknown', excerpt: '<script>window.readerInjected=true</script>' },
    ] } });
  });
  return { writes, remote, get reads() { return reads; } };
}

for (const theme of ['light', 'dark']) {
  test(`ticket preview renders Markdown and keeps exact unsaved edits in ${theme}`, async ({ page }, info) => {
    const fixture = await setup(page, 'fr', theme);
    await page.goto(`/analyses/${id}`);
    await page.getByRole('button', { name: 'Brouillon', exact: true }).click();
    const modal = page.getByRole('dialog', { name: 'Créer un ticket', exact: true });
    const reader = modal.getByRole('region', { name: 'Description', exact: true });
    await expect(modal.getByRole('button', { name: 'Aperçu', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(reader.getByRole('heading', { name: 'Besoin', exact: true })).toBeVisible();
    await expect(reader.getByRole('table').getByRole('row')).toHaveCount(2);
    await expect(reader.getByRole('checkbox')).toBeDisabled();
    await expect(reader.locator('.hljs-keyword').first()).toHaveText('SELECT');
    await expect(reader.locator('pre code')).toHaveText(sql);
    expect(fixture.writes).toHaveLength(0);
    await modal.getByRole('button', { name: 'Modifier', exact: true }).click();
    const editor = modal.getByLabel('Description', { exact: true });
    await expect(editor).toHaveValue(body);
    const edited = body + '\n\n### Exception ajoutée\n\nConserver ma correction manuelle.';
    await editor.fill(edited);
    await modal.getByRole('button', { name: 'Aperçu', exact: true }).click();
    await expect(reader.getByRole('heading', { name: 'Exception ajoutée', exact: true })).toBeVisible();
    expect(fixture.writes).toHaveLength(0);
    await page.screenshot({ path: `${info.outputDir}/ticket-reader-${theme}.png` });
    await modal.getByRole('button', { name: 'Modifier', exact: true }).click();
    await expect(editor).toHaveValue(edited);
    await modal.getByRole('button', { name: 'Enregistrer', exact: true }).click();
    expect(fixture.writes).toHaveLength(1);
    expect(fixture.writes[0]).toMatchObject({ body: edited });
    await modal.getByRole('button', { name: 'Fermer', exact: true }).first().click();
    await page.getByRole('button', { name: 'Brouillon', exact: true }).click();
    await expect(reader).toContainText('Conserver ma correction manuelle.');
    await expect(modal.getByRole('button', { name: 'Aperçu', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`source readers color code and safely render retained documents in ${theme}`, async ({ page }, info) => {
    const fixture = await setup(page, 'en', theme);
    await page.goto(`/analyses/${id}`);
    expect(fixture.reads).toBe(0);
    const sources = page.locator('.source-details');
    await sources.locator(':scope > summary').click();
    const query = sources.locator('.source-record').filter({ hasText: 'SQL check 1' });
    await query.locator(':scope > summary').click();
    await expect(query.locator('.hljs-keyword').first()).toHaveText('SELECT');
    expect(await query.locator('pre code').textContent()).toBe(sql);
    const code = sources.locator('.source-record').filter({ hasText: 'benefits/calculate.py' });
    await code.locator(':scope > summary').click();
    await expect(code.locator('.hljs-keyword').first()).toHaveText('def');
    for (const title of ['procedure.md', 'Documentation publique']) {
      const source = sources.locator('.source-record').filter({ hasText: title });
      await source.locator(':scope > summary').click();
      await expect(source.getByRole('heading', { name: 'Procédure' })).toBeVisible();
      await expect(source.getByRole('table').getByRole('row')).toHaveCount(2);
      await expect(source.locator('img,script,iframe,a[href^="javascript:"]')).toHaveCount(0);
      await source.getByRole('button', { name: 'Source text', exact: true }).click();
      expect(await source.locator('pre code').textContent()).toBe(documentMarkdown);
      await source.getByRole('button', { name: 'Read', exact: true }).click();
      await expect(source.getByRole('heading', { name: 'Procédure' })).toBeVisible();
    }
    const unknown = sources.locator('.source-record').filter({ hasText: 'sample.unknown' });
    await unknown.locator(':scope > summary').click();
    await expect(unknown.locator('.code-reader-heading')).toHaveText('Plain text');
    await expect(unknown.locator('script')).toHaveCount(0);
    expect(await page.evaluate(() => 'readerInjected' in window)).toBe(false);
    expect(fixture.remote).toHaveLength(0);
    expect(fixture.writes).toHaveLength(0);
    expect(fixture.reads).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `${info.outputDir}/source-reader-${theme}.png` });
  });
}

for (const language of ['en', 'fr'] as const) {
  test(`Git source excerpts show real line numbers and expand only on request in ${language}`, async ({ page }, info) => {
    const fixture = await setup(page, language, language === 'fr' ? 'light' : 'dark');
    const sourceLines = Array.from({length:30},(_,index)=>`const value${120+index} = ${120+index};`);
    await page.route(`**/api/analyses/${id}/messages/2/sources`, r => r.fulfill({json:{sources:[{
      id:'targeted-code',kind:'git',title:'src/calculation.ts',repository:'example/project',commit:'b'.repeat(40),
      line_start:120,line_end:149,preview_line_start:120,preview_line_end:149,excerpt:sourceLines.join('\n'),
    }]}}));
    await page.goto(`/analyses/${id}`);
    const sources = page.locator('.source-details');
    await sources.locator(':scope > summary').click();
    const source = sources.locator('.source-record').filter({hasText:'src/calculation.ts'});
    await source.locator(':scope > summary').click();
    await expect(source.getByText(language === 'fr' ? 'Lignes 120–131' : 'Lines 120–131',{exact:true})).toBeVisible();
    expect(await source.locator('pre code').textContent()).toBe(sourceLines.slice(0,12).join('\n'));
    await expect(source.locator('.code-line-numbers')).toHaveAttribute('aria-hidden','true');
    expect(await source.locator('.code-line-numbers').textContent()).toBe(Array.from({length:12},(_,i)=>120+i).join('\n'));
    const expand = source.getByRole('button',{name:language === 'fr' ? 'Afficher tout l’extrait (30 lignes)' : 'Show the full excerpt (30 lines)',exact:true});
    await expect(expand).toHaveAttribute('aria-expanded','false');
    await expand.click();
    expect(await source.locator('pre code').textContent()).toBe(sourceLines.join('\n'));
    await expect(source.getByText(language === 'fr' ? 'Lignes 120–149' : 'Lines 120–149',{exact:true})).toBeVisible();
    const collapse = source.getByRole('button',{name:language === 'fr' ? 'Réduire' : 'Show less',exact:true});
    await expect(collapse).toHaveAttribute('aria-expanded','true');
    await collapse.click();
    expect(await source.locator('pre code').textContent()).toBe(sourceLines.slice(0,12).join('\n'));
    expect(fixture.writes).toHaveLength(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`${info.outputDir}/targeted-source-${language}.png`});
  });
}
