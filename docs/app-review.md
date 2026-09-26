# App Store and Google Play review notes

What goes into App Store Connect's **App Review Information** and Play
Console's **App access**, and why. Research behind it:
[`research/2026-09-app-ux.md`](research/2026-09-app-ux.md) §0 (task U-1).

## 1. Why Cappy asks people to sign in first (Guideline 5.1.1(v))

Apple: *"If your app doesn't include significant account-based features, let
people use it without a login."* Cappy is members-only on purpose (GOAL 13),
and the server enforces it, not only the app. Paste this into the review
notes:

> Cappy is a members-only marketplace where private people and small
> businesses rent out their own workshops, machines, vans and storage by the
> hour. Every listing shows where a person's property is and when it stands
> empty. We show that only to signed-in, verifiable members, as Fat Llama and
> Getaround do, so that strangers cannot map when someone's garage or van is
> unattended.
>
> Every feature is tied to an account: searching and viewing listings (owner
> safety, above), booking and paying (Stripe, with the buyer's identity), the
> conversation between the two sides of a booking, reviews, payouts to owners
> (Stripe Connect, with identity checks), reporting and blocking.
>
> Before sign-in the app shows a welcome screen explaining what Cappy is,
> our legal pages (imprint, terms, privacy), how to report illegal content,
> and how to delete an account. Sign-up needs only an email address and a
> password.

If Apple rejects anyway, the fallback is ready as task U-2: a read-only
showcase of categories and example listings (no real addresses or
availability) before sign-in.

## 2. Demo accounts (Guideline 2.1)

Reviewers need working accounts that skip the email code. Create both in the
**production** user pool before submitting, confirmed by an admin so that no
code is sent:

```sh
aws cognito-idp admin-create-user --user-pool-id "$POOL" --username review-renter@cappy.app \
  --user-attributes Name=email,Value=review-renter@cappy.app Name=email_verified,Value=true \
  --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id "$POOL" --username review-renter@cappy.app \
  --password "$REVIEW_PASSWORD" --permanent
# The same again for review-owner@cappy.app
```

- **Renter** `review-renter@cappy.app`: can search, book and message. Give it a
  profile and a verified identity (Stripe Identity test outcome, or mark it
  verified in the payments database) so a booking above the ID threshold does
  not stop review.
- **Owner** `review-owner@cappy.app`: has two listings, one with instant book,
  and a Stripe Connect account that can be paid out.
- Payments in review use live Stripe. Tell the reviewer that a booking
  authorises the card and is released (nothing is charged) unless the owner
  accepts. Decline and refund the reviewer's test bookings from the admin
  console afterwards.
- Store the passwords in the team's password manager, never in this
  repository. Give them to Apple and Google only in the review forms, and
  rotate them after each review.
- The app never asks for an email code at sign-in: codes are sent only at
  sign-up and for a forgotten password. So the admin-confirmed accounts need
  none.

Google Play: **App access → All or some functionality is restricted**, with
the same two accounts and one line: "Sign in with the email and password
below; no code is needed."

## 3. Account deletion (Guideline 5.1.1(v), Play's account deletion policy)

- **In the app:** Profile → *Delete account* removes the profile, listings,
  saved items, push devices and notifications, then the Cognito user. Bookings,
  invoices and payment records are kept without personal data, as German
  commercial and tax law requires (10 years for invoices).
- **Without the app:** `https://<domain>/account/delete` is public. Give this
  URL in Play Console's *Data safety → Delete account URL*.
- **When deletion is refused:** deletion waits while a booking is still open
  or an owner's payout is pending. The server answers 409 `open_obligations`
  with the date the last booking ends, and the app shows it. Apple allows
  this if the app says why and when.

## 4. Sign in with Apple (Guideline 4.8)

Cappy offers only email and password today, so 4.8 does not apply. **If Google
(or any other third-party) sign-in is added, Sign in with Apple becomes
mandatory on iOS.** Deleting an account must then also revoke the Apple
tokens (`POST https://appleid.apple.com/auth/revoke`).

## 5. Other notes for the review form

- **Push:** the app asks for notification permission only after the first
  booking request or listing, never at launch (U-4).
- **Camera and photos:** used only for listing photos and hand-over
  evidence; the purpose strings are in `web/ios/App/App/Info.plist`.
- **Payments:** these are rentals of physical things between people, so
  Stripe is correct and in-app purchase is not required (Guideline 3.1.3(e)).
- **Minimum functionality (Guideline 4.2):** native push, the camera for
  hand-over evidence, universal and app links into bookings, and the Android
  back button. It is not a wrapped website.
- **User-generated content (Guideline 1.2):** every listing and profile can be
  reported (each message too, once U-13 ships), people can block each other, staff review reports,
  and the terms forbid objectionable content.

## 6. Before archiving a release build (iOS)

- **Associated domain:** both entitlement files read `applinks:$(CAPPY_DOMAIN)`.
  `CAPPY_DOMAIN` is a build setting of the App target (`cappy.app` in Debug and
  Release). Set it to the real domain before archiving. It must match the host
  that serves `/.well-known/apple-app-site-association` (written by the web
  build) and Android's `appLinkHost`.
- **Push environment:** Debug signs with `App/App.entitlements`
  (`aps-environment` development), Release with `App/App.release.entitlements`
  (production). An archive therefore uses production APNs; nothing to switch
  by hand.
- **Payment return:** a bank's card check returns to
  `https://$(CAPPY_DOMAIN)/pay/return?booking=…`, a universal link (`/pay/*`
  is in the association file and Android's intent filter), so it lands back
  in the app on the booking.
