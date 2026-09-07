# Lighthouse Audit — Sprint 24 (US-102)

Run against a real production build (`npm run build`, served locally with
`serve -s dist`), audited with `npx lighthouse` (v13.4.1) headless Chrome —
default mobile-throttled preset, matching the acceptance criterion
("Mobile performance: Lighthouse score > 90 on PWA"). Full HTML/JSON reports
are not committed (they're a point-in-time snapshot, not something to keep in
sync); re-run the commands below to reproduce.

Lighthouse 10+ removed the standalone PWA category (Chrome DevTools replaced
it with a manual installability checklist) — there is no single "PWA score"
this version of the tool can report. What's below is the four categories it
still scores.

## Results

| Page | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|
| `/login` (the app) | 96 | 100 | 100 | 63 |
| `/legal/privacy` (public page) | 95 | 100 | 100 | 100 |

## Why `/login`'s SEO score is 63, and why that's correct

The one point knocked off is `is-crawlable`: `robots.txt` (added this
sprint — there wasn't one before) deliberately disallows the whole app,
with explicit `Allow` exceptions for `/legal/` and `/listing/` (public
pages meant to be linked or shared). RentFlow's dashboard is an
authenticated SaaS app, not a marketing site — being excluded from search
indexing is the *correct* policy, not a defect, so this wasn't "fixed" by
loosening `robots.txt` to chase a number. The `/legal/privacy` run above,
against a page that's meant to be publicly discoverable, scores a clean 100
across every category with the same `robots.txt` in place — confirming the
63 on `/login` is `robots.txt` doing its job, not a broken page.

## Real issues found and fixed this pass

1. **Missing `<main>` landmark** (`landmark-one-main`, accessibility) — the
   shared `AuthLayout` (every login/register/password screen) and the new
   `LegalPageLayout` had no `<main>` element. Both now wrap their primary
   content in one; `AppShell` (the authenticated app shell) already had one.
2. **Insufficient color contrast** (`color-contrast`, accessibility) — a
   pre-existing "Protected by two-factor authentication" caption on the
   login page used `text-slate-400` at 12px (2.63:1 contrast against white,
   below WCAG's 4.5:1 minimum for text that size). Fixed to `text-slate-500`
   (the muted-text shade already used everywhere else in the app, e.g. the
   existing footer link and subtitle text one line above it) — one line
   this sprint's own new footer links were about to repeat the same mistake
   in, caught before it shipped rather than after.
3. **`robots.txt` returning the SPA's `index.html`** (`robots-txt`, SEO) —
   there was no `robots.txt` file at all, so every static host's SPA
   fallback served the React app's HTML in its place, which Lighthouse
   correctly read as 27 syntax errors. Added a real one (see above).

Accessibility now scores 100 on both pages audited; nothing chased past
that artificially (no ARIA added where a native element already suffices,
no contrast overridden below what the design's own muted-text shade allows).

## Performance: 95-96, not chased further

Both pages already sit above the 90 threshold on the mobile-throttled
preset. The two performance sub-audits that aren't a full 1.0 —
`first-contentful-paint` and a "reduce unused JavaScript" insight against
the shared `react`/`data`/`format` vendor chunks — are already the result of
the route-level code-splitting `App.tsx`'s own comment describes (Sprint
16, US-059): every screen past the front door is a separate lazy chunk
specifically so a caretaker on 3G isn't downloading the analytics charts to
see the login form. Squeezing the last few points would mean either
inlining critical CSS by hand or splitting the vendor chunks further, both
real engineering effort for a score that's already well clear of the
acceptance bar — left as a future optimization, not done reflexively here.

## Reproduce

```bash
cd frontend
npm run build
npx serve -s -l 4173 dist &
npx lighthouse http://localhost:4173/login \
  --output=json --output=html --output-path=/tmp/lh-login \
  --chrome-flags="--headless=new --no-sandbox --disable-gpu" \
  --only-categories=performance,accessibility,best-practices,seo
```
