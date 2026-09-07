# Native mobile app evaluation

**Status:** decision recorded, Sprint 26 · **Owner:** Kelvin · **Review:** when any
trigger in [§6](#6-what-would-change-this-decision) fires

The masterplan lists "native mobile app evaluation (based on PWA vs native app
usage data)" as a Phase 4 deliverable (masterplan.md:936), with React Native
apps as a post-traction expansion item (masterplan.md:1108). No sprint picked
it up, so the evaluation had never been written down. This is it.

**Decision: stay on the PWA. Do not build native apps yet.** The conditions
that would justify one are listed in §6, and none of them is met today.

---

## 1. What the PWA already does

The installed web app is not a fallback for a native app here — it covers the
whole of what the field workflow needs:

| Capability | How it is met today |
|---|---|
| Home-screen install | `vite-plugin-pwa` manifest, `InstallPrompt.tsx` |
| Works with no signal | IndexedDB action queue, FIFO replay with idempotency keys (`src/lib/offline-queue.ts`) |
| Push notifications | Web Push + VAPID, service worker click handling (`src/sw.ts`) |
| Camera capture | `<input capture>` for meter photos, maintenance photos, inspections |
| GPS tagging | `navigator.geolocation`, sent as `X-Geo-Position` |
| Biometric login | WebAuthn passkeys (US-108) |
| App shortcuts | Manifest `shortcuts` — record a payment, meter reading, report an issue |

The two things a native app would add that the PWA genuinely cannot are
**background sync while the app is closed** and **native SMS/USSD
interception**. Neither is load-bearing: the queue drains on next open and on
`online`, and M-Pesa confirmation arrives server-side through the Daraja
callback, not by reading the tenant's SMS inbox.

## 2. What a native app would cost

Two apps, not one. React Native shares the logic but not the release process,
the store review, the crash triage or the OS deprecation treadmill.

| Item | Estimate |
|---|---|
| Initial build (RN, both platforms, feature parity with the caretaker surface) | 8–10 sprint-weeks |
| Apple Developer + Google Play | ~USD 124 first year, USD 99/yr after |
| Ongoing: store releases, OS version breakage, crash triage | ~15–20% of one engineer, indefinitely |
| Second delivery pipeline (signing, TestFlight/internal track, staged rollout) | 1 sprint-week, then permanent overhead |

Against a single-maintainer team, that ongoing 15–20% is the number that
matters. It is not the build cost that kills a native app, it is the third year
of it.

## 3. What it would cost the users

This is the part that usually gets left out, and for this audience it dominates.

- **Install size.** A React Native binary is 25–40 MB. The PWA's cached shell
  is under 1 MB. On a prepaid bundle in Kayole that difference is real money,
  paid before the caretaker has recorded anything.
- **Device reality.** The caretaker devices this product is designed around are
  entry-level Androids — 2 GB RAM, often 32 GB storage that is already full.
  "Please uninstall something to install our app" is a conversion cliff a PWA
  simply does not have.
- **Update friction.** A PWA updates on next load. A native app updates when
  the user gets round to it, which for this cohort is "when the store forces
  it". Two versions of the payment recording flow in the field at once is a
  support burden and, with money involved, a correctness risk.
- **Distribution.** A landlord onboarding a caretaker sends a WhatsApp link
  today and the caretaker is working ninety seconds later. A store listing adds
  a search, an account, and a download over the same connection.

## 4. The data the masterplan asked us to decide on

The masterplan is explicit that this decision is to be made "based on PWA vs
native app usage data". That data does not exist yet — the platform has no
production users. Deciding now on speculation is exactly the mistake the
masterplan's phrasing was written to avoid, so the honest position is:

**not yet, and here is what we will measure.**

Instrumentation to add before the question can be reopened (none of it exists
today; this is the actual work item this evaluation produces):

1. **Install rate** — `beforeinstallprompt` shown vs `appinstalled` fired.
2. **Standalone usage share** — `display-mode: standalone` vs browser tab, per
   role. The number that matters is caretakers, not owners.
3. **Offline queue depth and drain latency** — already recorded per item in
   IndexedDB; not yet reported anywhere. If items routinely sit queued for
   hours, background sync becomes a real argument.
4. **Push opt-in and delivery rate** by platform. iOS Web Push has real
   limitations; if iOS caretakers turn out to matter, that is a genuine gap.
5. **Session abandonment on the install prompt** — how many people bounce at
   "Add to home screen".

## 5. The middle option, if it becomes necessary

If a store presence turns out to be needed for credibility rather than
capability — an agency procurement checklist asking "is there an app?" — the
cheap answer is a **Trusted Web Activity** (Android) wrapping the existing PWA.
It ships the same code, is listed in Play, and costs days rather than sprints.
That is the first move, not React Native.

## 6. What would change this decision

Any one of these is a trigger to reopen it, with the measurement from §4 in
hand:

- Standalone usage among caretakers stays **below 40%** after onboarding
  actively pushes install — meaning the PWA is not being adopted as an app.
- **Offline queue items routinely exceed 4 hours** before draining, meaning
  next-open sync is not good enough and true background sync is needed.
- **iOS becomes more than ~20% of caretaker devices** and Web Push limitations
  are measurably costing notifications.
- A **paying enterprise customer makes a store-listed app a contract
  condition** — in which case §5's TWA is evaluated first.
- Apple or Google materially restricts PWA capability on the specific APIs this
  product depends on (camera capture, geolocation, Web Push, WebAuthn).

## 7. Recommendation

Stay on the PWA. Spend the 8–10 sprint-weeks a native build would consume on
the four unbuilt Phase 5 sprints instead — SSO, subscription billing, the
general ledger and credit-bureau integration are all things a customer has
asked for, and a native app is not.

Add the §4 instrumentation in the next sprint that touches onboarding, so that
when this question is asked again there is data to answer it with rather than
another argument.
