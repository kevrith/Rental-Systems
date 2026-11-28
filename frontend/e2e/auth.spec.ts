import { expect, test } from '@playwright/test'

import { uniqueEmail, uniquePhone } from './support'

/**
 * Account creation, driven through the real UI form — the one journey in this
 * suite that is deliberately NOT done via the API, because it is the thing
 * every other spec's setup treats as already working. If registration itself
 * breaks, every other E2E test's `registerOwner` helper breaks the same way,
 * so this file is what actually tests the thing they all assume.
 */

test('a new owner can register and lands on their dashboard', async ({ page }) => {
  const email = uniqueEmail('owner')

  await page.goto('/register')

  await page.getByLabel('Full name').fill('Jane Wanjiru')
  await page.getByLabel(/Business or portfolio name/).fill('Wanjiru Rentals E2E')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Phone number').fill(uniquePhone())
  await page.getByLabel('Password').fill('E2e-Test-Password-1!')

  await page.getByRole('button', { name: 'Start free trial' }).click()

  // `/dashboard` redirects client-side to `/overview` (HomeRedirect).
  await expect(page).toHaveURL(/\/(dashboard|overview)/)
  await expect(page.getByText('Welcome back, Jane')).toBeVisible()
})

test('registering with an email already in use shows a server error, not a crash', async ({ page }) => {
  const email = uniqueEmail('owner')
  const phone = uniquePhone()

  const fillAndSubmit = async () => {
    await page.goto('/register')
    await page.getByLabel('Full name').fill('Jane Wanjiru')
    await page.getByLabel(/Business or portfolio name/).fill('Wanjiru Rentals E2E')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Phone number').fill(phone)
    await page.getByLabel('Password').fill('E2e-Test-Password-1!')
    await page.getByRole('button', { name: 'Start free trial' }).click()
  }

  await fillAndSubmit()
  // `/dashboard` redirects client-side to `/overview` (HomeRedirect).
  await expect(page).toHaveURL(/\/(dashboard|overview)/)

  // Same email and phone again, from a clean, signed-out tab.
  await page.evaluate(() => localStorage.clear())
  await fillAndSubmit()

  await expect(page).toHaveURL(/\/register/)
  await expect(page.getByRole('alert')).toBeVisible()
})

test('a tenant is shown how to ask their caretaker for a sign-in link', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('link', { name: 'Get a sign-in link' }).click()

  await expect(page).toHaveURL(/\/portal\/login/)

  // With SMS delivery off (the default) nothing is texted, so the page hands the
  // tenant a ready-made WhatsApp message instead of asking for a number to text.
  // The same page for every visitor: it cannot reveal whose tenant a number is.
  const ask = page.getByRole('link', { name: 'Ask your caretaker for a link' })
  await expect(ask).toBeVisible()
  await expect(ask).toHaveAttribute('href', /^https:\/\/wa\.me\/\?text=/)
})
