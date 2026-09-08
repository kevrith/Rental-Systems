import { expect, test } from '@playwright/test'

import { loadDemoData, registerOwner, signInAs } from './support'

/**
 * Every screen has to survive every screen size, from a 320px Galaxy Fold to a
 * desktop monitor — the caretaker app is used one-handed in a corridor and the
 * landlord signs off on the same data from a laptop.
 *
 * The check is deliberately mechanical rather than visual: a page fails when
 * its content is wider than the viewport, because that is the defect that
 * actually strands a user — a button pushed off the right edge cannot be
 * tapped, and no amount of pinch-zooming brings back a control the layout
 * never gave room to.
 *
 * `body.scrollWidth` is the measure, not `documentElement.scrollWidth`: the
 * latter counts content parked inside a horizontal scroll container, and wide
 * data tables (the pricing comparison, every list screen) are *supposed* to
 * scroll inside themselves. Elements are likewise only reported when no
 * ancestor clips or scrolls them, for the same reason.
 */

const VIEWPORTS = [
  { name: '320 (small phone)', width: 320, height: 640 },
  { name: '375 (iPhone SE)', width: 375, height: 667 },
  { name: '768 (tablet portrait)', width: 768, height: 1024 },
  { name: '1280 (laptop)', width: 1280, height: 800 },
]

const PUBLIC_ROUTES = ['/', '/login', '/register', '/help', '/legal/privacy', '/legal/terms']

const APP_ROUTES = [
  '/overview',
  '/properties',
  '/units',
  '/tenants',
  '/tenancies',
  '/payments',
  '/invoices',
  '/arrears',
  '/analytics',
  '/reports',
  '/maintenance',
  '/vendors',
  '/inspections',
  '/vacancies',
  '/applications',
  '/approvals',
  '/team',
  '/notifications',
  '/settings/profile',
  '/settings/organization',
]

/** Content the viewport cannot reach, plus the elements responsible for it. */
async function overflowReport(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const inner = window.innerWidth

    // Ground truth, and immune to the two things that make `scrollWidth`
    // lie: content parked inside a horizontal scroll container, and an open
    // dialog setting `body { overflow: hidden }`. If the page can be scrolled
    // sideways, something is off-screen; if it cannot, nothing is.
    const before = window.scrollX
    window.scrollTo(inner * 4, window.scrollY)
    const reachable = window.scrollX
    window.scrollTo(before, window.scrollY)

    // A fixed element is positioned against the viewport, so an ancestor's
    // `overflow` does not clip it — walking past one would wrongly excuse a
    // floating button that genuinely hangs off the edge.
    const clipped = (el: HTMLElement): boolean => {
      if (getComputedStyle(el).position === 'fixed') return false
      let parent = el.parentElement
      while (parent && parent !== document.documentElement) {
        const style = getComputedStyle(parent)
        const overflowX = style.overflowX
        if (overflowX === 'auto' || overflowX === 'scroll' || overflowX === 'hidden') return true
        if (style.position === 'fixed') return false
        parent = parent.parentElement
      }
      return false
    }

    const culprits: string[] = []
    for (const el of Array.from(document.querySelectorAll('*')) as HTMLElement[]) {
      const box = el.getBoundingClientRect()
      if (box.width === 0 || box.height === 0) continue
      if (box.right <= inner + 1 && box.left >= -1) continue
      if (clipped(el)) continue
      const cls = typeof el.className === 'string' ? el.className.slice(0, 110) : ''
      culprits.push(`${el.tagName.toLowerCase()} right=${Math.round(box.right)} [${cls}]`)
    }

    if (reachable <= 1 && culprits.length === 0) return null
    return { inner, reachable, culprits: culprits.slice(0, 5) }
  })
}

async function expectNoOverflow(page: import('@playwright/test').Page, route: string, viewport: string) {
  const report = await overflowReport(page)
  expect(
    report,
    report
      ? `${route} at ${viewport}: ${report.reachable}px of horizontal scroll, ${report.culprits.length} element(s) past the edge:\n  ${report.culprits.join('\n  ')}`
      : '',
  ).toBeNull()
}

test.describe('every screen fits every screen size', () => {
  for (const viewport of VIEWPORTS) {
    test(`public pages at ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      for (const route of PUBLIC_ROUTES) {
        await page.goto(route, { waitUntil: 'networkidle' })
        await expectNoOverflow(page, route, viewport.name)
      }
    })

    test(`app pages at ${viewport.name}`, async ({ page, request }) => {
      test.setTimeout(180_000)
      const session = await registerOwner(request)
      await loadDemoData(request, session.accessToken)
      await signInAs(page, session)

      await page.setViewportSize({ width: viewport.width, height: viewport.height })

      // The onboarding wizard opens over every route on a fresh account, and an
      // open dialog sets `body { overflow: hidden }` — which makes
      // `body.scrollWidth` report clipped content and read as a false 19px
      // overflow. Dismiss it once so the measurement is of the page itself.
      await page.goto('/overview', { waitUntil: 'networkidle' })
      const dismiss = page.getByRole('button', { name: "Don't show this again" })
      if (await dismiss.count()) await dismiss.click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      for (const route of APP_ROUTES) {
        await page.goto(route, { waitUntil: 'networkidle' })
        // A lapsed token bounces every route to /login, whose layout trivially
        // passes — that would report a clean bill of health for pages this test
        // never rendered.
        expect(new URL(page.url()).pathname, `${route} did not render`).toBe(route)
        await expectNoOverflow(page, route, viewport.name)
      }
    })
  }
})
