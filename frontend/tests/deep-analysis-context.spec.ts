import { test, expect } from './fixtures';

const id = '45454545-4545-4545-8545-454545454545';
const at = '2026-11-03T10:00:00Z';
function thread(need = 'Étudier une mise à jour directe depuis PostgreSQL') {
  return {
    id, title: 'PostgreSQL', need: 'Comment fonctionne la mise à jour ?', workflow: 'question',
    environment_id: 1, environment_name: 'Recette', status: 'DISCUSSING', conversation_state: 'DISCUSSION',
    created_at: at, latest_activity_at: at, analysis_protocol: '2.4', baseline: [], database: {},
    attachments: [], progress: [], error: '', understanding: '', questions: [], conversation: [],
    latest_version: null, versions: [], decision_revision: 0, decisions: [], decision_history: [], validated_version: null,
    messages: [
      { id: 1, role: 'user', kind: 'discussion', content: 'Comment fonctionne la mise à jour PostgreSQL ?', created_at: at },
      { id: 2, role: 'assistant', kind: 'discussion_reply', content: 'Souhaitez-vous étudier une mise à jour directe ?', created_at: at },
      { id: 3, role: 'user', kind: 'discussion', content: 'Oui.', created_at: at },
    ],
    discussion: { enabled: true, mode: 'discussion', revision: 3, connection_id: 1, job: null },
    analysis_runs: [], conversation_tickets: [], deep_analysis_need: need,
  };
}

for (const theme of ['light', 'dark']) {
  test(`one editable need, no message picker or launch on opening in ${theme}`, async ({ page }) => {
    let launched = 0;
    const value = thread();
    await page.emulateMedia({ colorScheme: theme as 'light' | 'dark' });
    await page.addInitScript(value => localStorage.setItem('spechelper-theme', value), theme);
    await page.route('**/api/**', r => r.fulfill({ json: [] }));
    await page.route('**/api/access/session', r => r.fulfill({ json: { authenticated: true, mode: 'local' } }));
    await page.route('**/api/settings', r => r.fulfill({ json: { name: 'SpecHelper', language: 'fr' } }));
    await page.route(`**/api/analyses/${id}`, r => r.fulfill({ json: value }));
    await page.route(`**/api/analyses/${id}/deep-analyze`, r => {
      expect(r.request().postDataJSON()).toEqual({ expected_revision: 3, intent: 'auto', subject: 'Vérifier la mise à jour des playlists archivées.' });
      launched++;
      return r.fulfill({ json: { ...value, status: 'QUEUED', conversation_state: 'IN_PROGRESS', discussion: { ...value.discussion, revision: 4, job: { id: 8, status: 'QUEUED', operation: 'analysis_preparation', created_at: at } } } });
    });
    await page.goto(`/analyses/${id}`);
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await page.getByRole('button', { name: 'Analyse approfondie', exact: true }).click();
    const modal = page.getByRole('dialog', { name: 'Analyse approfondie', exact: true });
    await expect(modal).toContainText('Précisez le besoin à analyser. SpecHelper utilisera les échanges et les sources pertinents de votre environnement.');
    const need = modal.getByLabel('Besoin à analyser', { exact: true });
    await expect(need).toHaveValue('Étudier une mise à jour directe depuis PostgreSQL');
    await expect(modal.locator('textarea')).toHaveCount(1);
    await expect(modal.locator('select,input[type=checkbox]')).toHaveCount(0);
    await expect(modal.getByRole('button')).toHaveCount(2);
    expect(launched).toBe(0);
    await need.fill('Vérifier la mise à jour des playlists archivées.');
    await modal.getByRole('button', { name: 'Lancer l’analyse approfondie', exact: true }).click();
    await expect(modal).not.toBeVisible();
    expect(launched).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('ambiguous need stays empty and a failed launch preserves the edited need', async ({ page }) => {
  let launches = 0;
  await page.route('**/api/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/access/session', r => r.fulfill({ json: { authenticated: true, mode: 'local' } }));
  await page.route('**/api/settings', r => r.fulfill({ json: { name: 'SpecHelper', language: 'fr' } }));
  await page.route(`**/api/analyses/${id}`, r => r.fulfill({ json: thread('') }));
  await page.route(`**/api/analyses/${id}/deep-analyze`, r => { launches++; return r.fulfill({ status: 409, json: { detail: 'Please retry.' } }); });
  await page.goto(`/analyses/${id}`);
  await page.getByRole('button', { name: 'Analyse approfondie', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Analyse approfondie', exact: true });
  const need = modal.getByLabel('Besoin à analyser', { exact: true });
  await expect(need).toHaveValue('');
  const launch = modal.getByRole('button', { name: 'Lancer l’analyse approfondie', exact: true });
  await expect(launch).toBeDisabled();
  await need.fill('Vérifier les règles d’archivage des playlists.');
  await launch.click();
  await expect(modal.getByRole('alert')).toBeVisible();
  await expect(need).toHaveValue('Vérifier les règles d’archivage des playlists.');
  expect(launches).toBe(1);
  await modal.getByRole('button', { name: 'Annuler', exact: true }).click();
  await expect(modal).not.toBeVisible();
});

test('context preparation uses real progress, hides selection JSON and retries the same need', async ({ page }) => {
  let retries = 0;
  const need = 'Vérifier la mise à jour PostgreSQL';
  const job = { id: 8, kind: 'discussion', operation: 'analysis_preparation', status: 'ERROR', created_at: at,
    waiting_reason: '', waiting_causes: [], phases: [{ key: 'selection', status: 'error', events: [], response_preview: 'PRIVATE_SELECTION_JSON' }] };
  const value = { ...thread(need), status: 'ERROR', conversation_incident: true,
    discussion: { ...thread().discussion, job }, work_progress: [job],
    analysis_runs: [{ number: 1, status: 'PARTIAL', steps: [] }],
  };
  await page.route('**/api/**', r => r.fulfill({ json: [] }));
  await page.route('**/api/access/session', r => r.fulfill({ json: { authenticated: true, mode: 'local' } }));
  await page.route('**/api/settings', r => r.fulfill({ json: { name: 'SpecHelper', language: 'fr' } }));
  await page.route(`**/api/analyses/${id}`, r => r.fulfill({ json: value }));
  await page.route(`**/api/analyses/${id}/deep-analyze`, r => {
    expect(r.request().postDataJSON()).toEqual({ expected_revision: 3, intent: 'auto', subject: need });
    retries++; return r.fulfill({ json: { ...value, status: 'QUEUED', conversation_state: 'IN_PROGRESS', discussion: { ...value.discussion, job: { ...job, status: 'QUEUED' } } } });
  });
  await page.goto(`/analyses/${id}`);
  await expect(page.getByText('Préparation de l’analyse interrompue', { exact: true })).toBeVisible();
  await expect(page.getByText('PRIVATE_SELECTION_JSON')).toHaveCount(0);
  await page.getByRole('button', { name: 'Réessayer', exact: true }).click();
  expect(retries).toBe(1);
});
