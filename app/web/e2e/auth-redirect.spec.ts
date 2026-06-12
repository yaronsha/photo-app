import { test, expect, type Page } from '@playwright/test';

// Auth is disabled in e2e (no VITE_SUPABASE_* env), so the LoginPage banner
// isn't exercised here. What we verify is the always-on behavior: a Supabase
// OAuth error redirect must be scrubbed from the URL and its verbose
// `error_description` must never reach the page.

async function mockApi(page: Page) {
  await page.route('**/search**', route =>
    route.fulfill({ json: { results: [], has_more: false } }),
  );
  await page.route('**/people', route => route.fulfill({ json: [] }));
}

const ERROR_QUERY =
  '?error=server_error&error_code=unexpected_failure' +
  '&error_description=Database+error+saving+new+user';

test.describe('Supabase auth-error redirect', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test('strips error params from the query string on load', async ({ page }) => {
    await page.goto(`/${ERROR_QUERY}`);
    // replaceState runs synchronously at module load, before paint.
    await expect(page).toHaveURL(/\/(\?.*)?$/);
    const url = new URL(page.url());
    expect(url.searchParams.has('error')).toBe(false);
    expect(url.searchParams.has('error_code')).toBe(false);
    expect(url.searchParams.has('error_description')).toBe(false);
  });

  test('strips error params from the hash fragment on load', async ({ page }) => {
    await page.goto(`/#error=server_error&error_description=Database+error+saving+new+user`);
    expect(page.url()).not.toContain('error_description');
    expect(page.url()).not.toContain('error=');
  });

  test('never leaks the raw error_description into the page', async ({ page }) => {
    await page.goto(`/${ERROR_QUERY}`);
    await expect(page.locator('body')).not.toContainText('Database error saving new user');
  });

  test('preserves unrelated query params while removing error keys', async ({ page }) => {
    await page.goto(`/?date_from=2020-01-01&error=server_error&error_description=secret`);
    const url = new URL(page.url());
    expect(url.searchParams.get('date_from')).toBe('2020-01-01');
    expect(url.searchParams.has('error')).toBe(false);
    expect(url.searchParams.has('error_description')).toBe(false);
  });
});
