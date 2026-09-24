import { Component, type ReactNode } from 'react'
import { Button } from './ui.tsx'
import { Icon } from './Icon.tsx'

type Props = { children: ReactNode }
type State = { error: Error | null }

/** A blank screen tells someone nothing. If the tree dies they get a plain
 *  explanation, a way out, and their data left intact. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error('[cappy] render failed', error)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="mx-auto flex min-h-dvh max-w-[520px] flex-col items-center justify-center px-6 text-center">
        <span className="mb-4 grid h-12 w-12 place-items-center rounded-[var(--radius-control)] bg-[var(--danger-subtle)] text-[var(--danger)]">
          <Icon name="alert" size={26} />
        </span>
        <h1 className="t-h3 mb-2">This screen stopped working</h1>
        <p className="t-body mb-6 text-[var(--ink-3)]">
          Something in the app broke while drawing this page. Your bookings and listings
          are safe. Going back to Browse usually clears it.
        </p>
        <Button size="lg" onClick={() => (location.href = '/')}>
          Back to Browse
        </Button>
        <p className="t-sm mt-6 font-mono text-[var(--ink-4)]">{this.state.error.message}</p>
      </div>
    )
  }
}
