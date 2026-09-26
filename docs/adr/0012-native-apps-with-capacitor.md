# 0012. App Store and Google Play through Capacitor

## Context
Cappy ships on the web, the App Store and Google Play. The product is one
React app. Writing it twice more (Swift, Kotlin) or porting it to React
Native would triple the surface to build and to verify, for a product whose
screens are lists, forms, photos and a card form.

## Decision
The same `web/` build runs inside Capacitor shells for iOS and Android
(`web/ios`, `web/android`, created with `npx cap add`).

- **API**: native builds set `VITE_API_URL=https://<domain>/api`. Their
  origins (`capacitor://localhost` on iOS, `https://localhost` on Android) are
  listed in the gateway's `CORS_ORIGINS`. The web keeps same-origin calls.
- **Media**: photo URLs the API returns relative (`/media/…`) are resolved
  against the API origin, so they work on the web and in a shell alike.
- **Sign-in**: Cognito over HTTPS from the app, as on the web. The refresh
  token lives in the shell's web storage (as on the web, under the CSP).
- **Payments**: Stripe's Payment Element runs inside the web view. Apple and
  Google allow external payment for physical goods and services used outside
  the app (rentals of real machines and spaces), so no in-app purchase is
  needed.
- **Deep links**: `/.well-known/apple-app-site-association` and
  `/.well-known/assetlinks.json` are served by the web app, generated at build
  time from the Apple team id and Android signing fingerprint (build variables).
- **Store rules** met in the app: account deletion in the app (`DELETE /me`
  plus Cognito `DeleteUser`); a data export; privacy policy and terms pages;
  no sign-in-with-third-party (so no Sign in with Apple requirement).

## Rejected
- *React Native.* A rewrite of every screen, and a second app to verify.
- *PWA only.* The App Store does not list PWAs.

## Consequences
One codebase, one verification pass, three stores. Native-only features
(push notifications, camera tuned for listing photos) come through Capacitor
plugins when they are worth adding. Push is the first candidate: today's
notifications are email only.

## Correction (2026-09-26)

Two statements above are out of date. The refresh token is kept in Capacitor
Preferences (UserDefaults / SharedPreferences), not web-view storage, and
backups and device transfers exclude it on Android; moving it into the
Keychain and Keystore is U-17. Notifications are not email only: push through
SNS Mobile Push (APNs, FCM) is built, asked for after the first booking
request or listing. The shells also run without a CSP of their own (P-5).
The decision itself stands.
