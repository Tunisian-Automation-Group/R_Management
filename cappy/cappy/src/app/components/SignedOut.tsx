import { useNavigate } from 'react-router-dom'
import { Button, EmptyState } from './ui.tsx'

/**
 * What a screen shows when it needs a person and there is none. Browsing is
 * open; bookings, listings, hearts and the record behind them are someone's.
 */
export function SignedOut({ what, next }: { what: string; next: string }) {
  const nav = useNavigate()
  const to = (mode: 'in' | 'up') => nav(`/login?mode=${mode}&next=${encodeURIComponent(next)}`)
  return (
    <EmptyState
      icon="user"
      title="Sign in to continue"
      body={`You need an account to ${what}. It takes a minute, and one account both buys hours and sells them.`}
      action={
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-center">
          <Button size="lg" onClick={() => to('in')}>
            Sign in
          </Button>
          <Button size="lg" variant="secondary" onClick={() => to('up')}>
            Create an account
          </Button>
        </div>
      }
    />
  )
}
