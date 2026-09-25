import { useMemo, useState, type FormEvent } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import { Banner, Button } from './ui.tsx'

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
  return (
    <Elements stripe={stripe} options={{ clientSecret }}>
      <Form bookingId={bookingId} onPaid={onPaid} />
    </Elements>
  )
}

function Form({ bookingId, onPaid }: { bookingId: string; onPaid: () => void }) {
  const stripe = useStripe()
  const elements = useElements()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return
    setBusy(true)
    setError(null)
    const { error: failed } = await stripe.confirmPayment({
      elements,
      // Only methods that leave the page (a bank redirect) come back here.
      confirmParams: { return_url: `${location.origin}/bookings/${bookingId}` },
      redirect: 'if_required',
    })
    setBusy(false)
    if (failed) setError(failed.message ?? 'The payment did not go through.')
    else onPaid()
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-4 pb-2">
      <PaymentElement />
      {error && <Banner tone="danger" title="Payment not authorised" body={error} />}
      <Button type="submit" block size="lg" disabled={!stripe || busy}>
        {busy ? 'Authorising…' : 'Hold the amount and send'}
      </Button>
    </form>
  )
}
