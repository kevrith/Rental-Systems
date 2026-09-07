# Dark mode

**Status: the infrastructure and the shared component kit are done and
correct. Most individual feature pages are not — see "What's left" below for
exactly what that means and how to finish one.**

## What exists

- **Class-based, not OS-preference-based.** Toggled by `.dark` on `<html>`
  (`src/store/theme-store.ts`), so a user's choice sticks regardless of what
  their OS is set to. Falls back to `prefers-color-scheme` only on first
  visit, before any explicit choice has been made; after that, `localStorage`
  wins.
- **The Tailwind 4 custom variant** is registered in `src/index.css`:
  `@custom-variant dark (&:where(.dark, .dark *));`. Every `dark:` utility in
  the codebase depends on this line existing.
- **Three new colour steps** (`-300` / `-400`) on `money`, `warn` and
  `danger` in the same file's `@theme` block — the existing ramp only went
  from a pale `-100` straight to a saturated `-500`/`-600`/`-700`, which is
  the wrong end of the ramp for light text on a dark, tinted background.
  Nothing in light mode reads these; every dark-mode badge/alert treatment
  does.
- **`ThemeToggle`** (`src/components/ThemeToggle.tsx`) — the sun/moon button
  in the app header.
- **Every primitive in `src/components/ui/index.tsx`** — `Button`, `Card`
  (+ `CardHeader`/`CardTitle`/`CardDescription`/`CardBody`), `Badge` (all six
  tones), `Label`/`Input`/`Textarea`/`Select`/`Field`, `Alert` (all four
  tones), `Table`/`Th`/`Td`, `EmptyState`, `Skeleton`, `Dialog`, `Tabs`/`Tab`.
  Because nearly every screen composes these rather than raw HTML, this one
  file is most of the app's actual visual surface.
- **`AppShell.tsx`** — the sidebar, header, mobile drawer, nav list and user
  footer that frame every authenticated screen.
- **`DashboardPage.tsx`** — done end to end, as the worked example the
  pattern below is extracted from.

## What's left

Every other feature page (`src/features/**/*.tsx`) was written before dark
mode existed and reaches for raw Tailwind slate/white utilities directly
(`bg-white`, `text-slate-900`, `border-slate-200`, ...) instead of composing
`Card`/`Table`/etc. Those raw utilities do not get a dark counterpart for
free — Tailwind classes are literal, so `text-slate-900` means exactly that
in both themes unless a `dark:` companion class is added next to it.

**Toggling dark mode today will make those pages' surrounding chrome (nav,
header, dialogs, buttons, tables) look correct while their own raw-styled
content stays light-mode-only** — readable-but-jarring, not broken.

Finishing a page is mechanical:

```bash
# From frontend/ — find every raw color utility on one page.
grep -n "bg-white\|text-slate-900\|text-slate-700\|text-slate-600\|text-slate-500\|text-slate-400\|border-slate-200\|border-slate-100\|bg-slate-50\|bg-slate-100" \
  src/features/tenants/TenantDetailPage.tsx
```

For each hit, add the matching `dark:` class next to it. The mapping used
everywhere else in this codebase (kept consistent on purpose, so a page never
looks different in intent from `AppShell` or the primitives):

| Light | Dark companion |
|---|---|
| `bg-white` | `dark:bg-slate-900` |
| `bg-slate-50` | `dark:bg-slate-800` (or `dark:bg-slate-800/50` for a subtler tint) |
| `bg-slate-100` | `dark:bg-slate-800` |
| `bg-slate-200` | `dark:bg-slate-700` |
| `text-slate-900` | `dark:text-slate-100` |
| `text-slate-700` | `dark:text-slate-300` |
| `text-slate-600` | `dark:text-slate-400` |
| `text-slate-500` | `dark:text-slate-400` |
| `text-slate-400` | `dark:text-slate-500` |
| `border-slate-200` | `dark:border-slate-700` |
| `border-slate-100` | `dark:border-slate-800` |
| `hover:bg-slate-50` / `-100` / `-200` | `dark:hover:bg-slate-800` (or `-700` for the `-200` case) |
| A tinted badge/alert background (`bg-{brand,money,warn,danger,sky}-50`) | `dark:bg-{color}-700/25 dark:text-{color}-300` (or `-900/40` + `-300` for `brand`/`sky`, which have a `-900` step) |

Solid, saturated buttons (`bg-danger-600 text-white`, `bg-money-600
text-white`, `bg-brand-600 text-white`) need **no** dark companion — a
saturated colour with white text already has enough contrast on both
backgrounds, which is why `Button`'s `primary`/`danger`/`success` variants
were left alone.

After editing, `npx tsc -b --noEmit` and `npx oxlint` catch nothing dark-mode
specific — the only real check is visual: toggle the theme switch and look at
the page. There is no automated test for colour contrast in this codebase
today.

## Why this scope and not a shortcut

A blanket CSS trick (`.dark img { filter: invert(1) }`-style "smart invert")
was considered and rejected — it would have covered every page in one commit,
but produces visibly wrong results on photos, charts and anything with its
own colour meaning (a red "overdue" badge inverting to a confusing green),
which actively works against "dark mode should feel professional," the
reason this was requested. Token-based, page-by-page dark mode is more work
up front and is the only version that looks like it was designed rather than
patched on.
