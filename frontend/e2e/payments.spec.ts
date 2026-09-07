import { expect, test } from '@playwright/test'

import { loadDemoData, registerOwner, signInAs } from './support'

/**
 * Recording a payment: the single highest-risk path in the app, and the one
 * the ranked "what's missing" review named explicitly. A defect here is not a
 * cosmetic bug, it is a tenant's rent going unrecorded or a receipt never
 * reaching them — which is exactly the class of bug a component-level test
 * cannot catch, because it depends on the real API allocating the payment
 * against a real invoice and the real page navigating to a real receipt.
 */

test.beforeEach(async ({ page, request }) => {
  const owner = await registerOwner(request)
  await loadDemoData(request, owner.accessToken)
  await signInAs(page, owner)
})

test('recording a cash payment allocates it and lands on a confirmed receipt', async ({ page }) => {
  await page.goto('/payments/new')

  await page.getByLabel('Tenancy').selectOption({ index: 1 })
  await page.getByLabel('Amount (KES)').fill('5000')

  await page.getByRole('button', { name: 'Record payment' }).click()

  await expect(page).toHaveURL(/\/payments\/[0-9a-f-]+$/)
  await expect(page.getByText('KES 5,000.00').first()).toBeVisible()
  await expect(page.getByText('Confirmed')).toBeVisible()
})

test('the new payment appears in the payments list', async ({ page }) => {
  await page.goto('/payments/new')
  await page.getByLabel('Tenancy').selectOption({ index: 1 })
  await page.getByLabel('Amount (KES)').fill('7500')
  await page.getByRole('button', { name: 'Record payment' }).click()
  await expect(page).toHaveURL(/\/payments\/[0-9a-f-]+$/)

  await page.goto('/payments')

  await expect(page.getByRole('table').getByText('KES 7,500.00')).toBeVisible()
})

test('the submit button is disabled until a tenancy and an amount are both set', async ({ page }) => {
  await page.goto('/payments/new')

  const submit = page.getByRole('button', { name: 'Record payment' })
  await expect(submit).toBeDisabled()

  await page.getByLabel('Tenancy').selectOption({ index: 1 })
  await expect(submit).toBeDisabled()

  await page.getByLabel('Amount (KES)').fill('1000')
  await expect(submit).toBeEnabled()
})
