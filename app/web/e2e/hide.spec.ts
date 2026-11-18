import { test, expect, type Page } from '@playwright/test';

const PHOTO = {
  id: 'p1',
  caption: 'kids at the beach',
  taken_at: '2020-01-01T12:00:00+00:00',
  thumb_url: '/thumb/p1',
  score: 0,
  location_name: null,
  tags: [],
  people: [],
  activities: [],
  content_type: 'photo',
  subject_type: null,
  setting_type: null,
  sharpness: null,
  face_clarity_score: null,
  primary_focus: null,
  indoor_outdoor: null,
  hidden: false,
};

async function mockApi(page: Page, isAdmin: boolean) {
  const calls: string[] = [];
  await page.route('**/api/me', route =>
    route.fulfill({ json: { auth_enabled: false, is_admin: isAdmin } }),
  );
  await page.route('**/people', route => route.fulfill({ json: [] }));
  await page.route('**/search**', route => {
    calls.push(route.request().url());
    route.fulfill({ json: { results: [PHOTO], has_more: false } });
  });
  await page.route('**/photo/p1/info', route => route.fulfill({ json: PHOTO }));
  await page.route('**/photo/p1/hide', route => {
    calls.push('POST hide');
    route.fulfill({ json: { id: 'p1', hidden: true } });
  });
  await page.route(/\/(thumb|photo)\/p1$/, route => route.fulfill({ status: 404 }));
  return calls;
}

test('admin can hide a photo and see the Hidden view', async ({ page }) => {
  const calls = await mockApi(page, true);
  await page.goto('/?q=beach');

  await page.getByRole('button', { name: 'Hidden photos' }).click();
  await expect.poll(() => calls.some(c => c.includes('hidden=only'))).toBe(true);
  await page.getByRole('button', { name: 'Hidden photos' }).click();

  await page.getByRole('img', { name: 'kids at the beach' }).first().click();
  await page.getByRole('button', { name: 'Hide photo' }).click();
  await expect(page.getByRole('status')).toContainText('Photo hidden');
  expect(calls).toContain('POST hide');

  // Viewer closes instead of sliding to another photo, and the hidden photo
  // leaves the grid without refetching the list.
  await expect(page.getByRole('dialog', { name: 'Photo viewer' })).toHaveCount(0);
  await expect(page.getByText('No photos found')).toBeVisible();
});

test('non-admin sees no hide controls', async ({ page }) => {
  await mockApi(page, false);
  await page.goto('/?q=beach');
  await page.getByRole('img', { name: 'kids at the beach' }).first().click();
  await expect(page.getByText('Download High Res')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Hide photo' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Hidden photos' })).toHaveCount(0);
});
