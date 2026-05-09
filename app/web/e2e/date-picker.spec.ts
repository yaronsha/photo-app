import { test, expect, type Page } from '@playwright/test';

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_MONTH = new Date().getMonth(); // 0-indexed
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

const APP_BASE = '/static/';

async function mockApi(page: Page) {
  await page.route('**/search**', route =>
    route.fulfill({ json: { results: [], has_more: false } }),
  );
  await page.route('**/people', route => route.fulfill({ json: [] }));
}

async function openPicker(page: Page) {
  await page.getByRole('button', { name: 'Open date range picker' }).click();
  // Wait for dialog to appear
  await expect(page.getByRole('dialog', { name: 'Date range picker' })).toBeVisible();
}

function fromPicker(page: Page) {
  return page.getByTestId('from-picker');
}

function toPicker(page: Page) {
  return page.getByTestId('to-picker');
}

// ─── From selection ──────────────────────────────────────────────────────────

test.describe('DateRangePicker — From selection', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto(APP_BASE);
    await openPicker(page);
  });

  test('selecting From month in a past year updates chip and URL', async ({ page }) => {
    const from = fromPicker(page);
    const yearsBack = CURRENT_YEAR - 2020;

    for (let i = 0; i < yearsBack; i++) {
      await from.getByRole('button', { name: 'Previous year' }).click();
    }

    // Verify From picker shows 2020
    await expect(from.getByRole('button', { name: /2020/ })).toBeVisible();

    await from.getByRole('button', { name: 'Jan' }).click();

    await expect(page).toHaveURL(/date_from=2020-01-01/);
    await expect(
      page.getByRole('button', { name: 'Open date range picker' }),
    ).toContainText('Jan 2020');
  });

  test('selecting From month in current year updates chip and URL', async ({ page }) => {
    const from = fromPicker(page);

    // Already on current year; Jan should be enabled
    await from.getByRole('button', { name: 'Jan' }).click();

    await expect(page).toHaveURL(new RegExp(`date_from=${CURRENT_YEAR}-01-01`));
    await expect(
      page.getByRole('button', { name: 'Open date range picker' }),
    ).toContainText(`Jan ${CURRENT_YEAR}`);
  });
});

// ─── Bounds enforcement ───────────────────────────────────────────────────────

test.describe('DateRangePicker — bounds enforcement', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto(APP_BASE);
    await openPicker(page);
  });

  test('Previous year arrow disabled at 1920', async ({ page }) => {
    const from = fromPicker(page);
    const prevBtn = from.getByRole('button', { name: 'Previous year' });

    const yearsBack = CURRENT_YEAR - 1920;
    for (let i = 0; i < yearsBack; i++) {
      await prevBtn.click();
    }

    await expect(prevBtn).toBeDisabled();
  });

  test('Next year arrow disabled at current year', async ({ page }) => {
    const from = fromPicker(page);
    await expect(from.getByRole('button', { name: 'Next year' })).toBeDisabled();
  });

  test('future months in current year are disabled', async ({ page }) => {
    const from = fromPicker(page);

    if (CURRENT_MONTH < 11) {
      await expect(from.getByRole('button', { name: MONTHS[CURRENT_MONTH + 1] })).toBeDisabled();
    }
  });
});

// ─── From ≤ To constraint ────────────────────────────────────────────────────

test.describe('DateRangePicker — From ≤ To constraint', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto(APP_BASE);
    await openPicker(page);
  });

  test('From months after To date are disabled', async ({ page }) => {
    const from = fromPicker(page);
    const to = toPicker(page);

    // Set To = Jan 2020
    const toYearsBack = CURRENT_YEAR - 2020;
    for (let i = 0; i < toYearsBack; i++) {
      await to.getByRole('button', { name: 'Previous year' }).click();
    }
    await to.getByRole('button', { name: 'Jan' }).click();

    // From picker still shows current year; all months should be disabled (max is Jan 2020)
    // Navigate From to 2021 — all months disabled there
    const fromYearsBack = CURRENT_YEAR - 2021;
    for (let i = 0; i < fromYearsBack; i++) {
      await from.getByRole('button', { name: 'Previous year' }).click();
    }

    await expect(from.getByRole('button', { name: 'Jan' })).toBeDisabled();
    await expect(from.getByRole('button', { name: 'Dec' })).toBeDisabled();
  });
});

// ─── Clear all ────────────────────────────────────────────────────────────────

test.describe('DateRangePicker — Clear all', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto(`${APP_BASE}?date_from=2020-01-01&date_to=2022-12-31`);
    await openPicker(page);
  });

  test('Clear all removes both dates from URL', async ({ page }) => {
    await page.getByRole('button', { name: 'Clear all' }).click();
    await expect(page).not.toHaveURL(/date_from/);
    await expect(page).not.toHaveURL(/date_to/);
  });

  test('After Clear all, From picker resets to month view at current year', async ({ page }) => {
    const from = fromPicker(page);
    await page.getByRole('button', { name: 'Clear all' }).click();

    // Month view visible (Jan button present)
    await expect(from.getByRole('button', { name: 'Jan' })).toBeVisible();
    // Header shows current year
    await expect(from.getByRole('button', { name: new RegExp(String(CURRENT_YEAR)) })).toBeVisible();
  });
});

// ─── Year view navigation ────────────────────────────────────────────────────

test.describe('DateRangePicker — year view navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto(APP_BASE);
    await openPicker(page);
  });

  test('clicking year label drills into year view', async ({ page }) => {
    const from = fromPicker(page);
    await from.getByRole('button', { name: new RegExp(String(CURRENT_YEAR)) }).click();
    await expect(from.getByRole('button', { name: 'Back to months' })).toBeVisible();
  });

  test('Back to months returns to month view', async ({ page }) => {
    const from = fromPicker(page);
    await from.getByRole('button', { name: new RegExp(String(CURRENT_YEAR)) }).click();
    await from.getByRole('button', { name: 'Back to months' }).click();
    await expect(from.getByRole('button', { name: 'Jan' })).toBeVisible();
  });

  test('selecting year in year view navigates to month view for that year', async ({ page }) => {
    const from = fromPicker(page);
    await from.getByRole('button', { name: new RegExp(String(CURRENT_YEAR)) }).click();

    // Click year 2022 in year view
    await from.getByRole('button', { name: '2022' }).click();

    // Should be back in month view showing 2022
    await expect(from.getByRole('button', { name: /2022/ })).toBeVisible();
    await expect(from.getByRole('button', { name: 'Jan' })).toBeVisible();
  });
});
