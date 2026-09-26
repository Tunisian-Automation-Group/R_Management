import { useMemo, useState, type FormEvent } from 'react'
// The pure entry injects Stripe.js only when loadStripe runs, not on import:
// no third-party script before someone reaches a payment (V3-1, § 25 TDDDG).
import { loadStripe } from '@stripe/stripe-js/pure'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import { Banner, Button } from './ui.tsx'
import { Icon } from './Icon.tsx'
import { useOnline } from './Offline.tsx'
import { lang, t } from '../../i18n.ts'
import { payReturnUrl } from '../../data/repo.ts'

/**
 * The card step, with Stripe's Payment Element. Stripe handles the card and
 * any bank check (SCA); the card is authorised, not charged, and the owner is
 * asked once Stripe tells Cappy it went through.
 */
export function PayStep({
  publishableKey,
  clientSecret,
  bookingId,
  onPaid,
}: {
  publishableKey: string
  clientSecret: string
  bookingId: string
  onPaid: () => void
}) {
  // Stripe.js loads only for the people who get this far.
  const stripe = useMemo(() => loadStripe(publishableKey), [publishableKey])
  // The card form wears Cappy's tokens, in light and dark (UX-24): read from
  // the page so a theme change needs nothing here.
  const appearance = useMemo(() => {
    const css = getComputedStyle(document.documentElement)
    const v = (name: string) => css.getPropertyValue(name).trim()
    return {
      theme: document.documentElement.dataset.theme === 'dark' ? ('night' as const) : ('stripe' as const),
      variables: {
        colorPrimary: v('--accent'),
        colorBackground: v('--surface'),
        colorText: v('--ink'),
        colorTextSecondary: v('--ink-3'),
        colorDanger: v('--danger'),
        fontFamily: v('--font-sans'),
        borderRadius: v('--radius-s'),
        focusBoxShadow: `0 0 0 2px ${v('--focus')}`,
      },
    }
  }, [])
  return (
    <Elements stripe={stripe} options={{ clientSecret, locale: lang(), appearance }}>
      <Form bookingId={bookingId} onPaid={onPaid} />
    </Elements>
  )
}

function Form({ bookingId, onPaid }: { bookingId: string; onPaid: () => void }) {
  const stripe = useStripe()
  const elements = useElements()
  const online = useOnline()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return
    setBusy(true)
    setError(null)
    const { error: failed } = await stripe.confirmPayment({
      elements,
      // Only methods that leave the page (a bank check, a redirect) come back,
      // to /pay/return on Cappy's own domain: in the store apps that is a
      // universal / app link, so the bank hands back to the app (U-7, FL-19).
      confirmParams: { return_url: payReturnUrl(bookingId) },
      redirect: 'if_required',
    })
    setBusy(false)
    if (failed) setError(failed.message ?? t('The payment did not go through.'))
    else onPaid()
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4 pb-2">
      {/* An enclosed panel with who handles the card reads as the secure part
          of the page (UX-24, Baymard's perceived-security research). */}
      <div className="rounded-[var(--radius-m)] border border-[var(--line-strong)] bg-[var(--surface)] p-4">
        <p className="t-sm mb-3 flex items-center gap-2 font-semibold text-[var(--ink-2)]">
          <Icon name="shield" size={15} strokeWidth={2.2} className="text-[var(--success)]" />
          {t('Card details go to Stripe, never to Cappy')}
        </p>
        <PaymentElement />
      </div>
      {error && <Banner tone="danger" title={t('Payment not authorised')} body={error} />}
      {/* The click that binds the buyer: §312j BGB wants it to say so. */}
      <Button type="submit" block size="lg" disabled={!stripe || busy || !online}>
        {busy ? t('Authorising…') : t('Book and pay')}
      </Button>
      {/* U-34: what paying here buys, next to the button that does it. */}
      <p className="t-sm text-center text-[var(--ink-3)]">
        {t('Cappy holds your payment and pays the owner only once the booking has happened. Paying outside Cappy loses that protection.')}
      </p>
    </form>
  )
}
