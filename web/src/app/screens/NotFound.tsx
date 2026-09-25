import { useNavigate } from 'react-router-dom'
import { Screen } from '../components/AppShell.tsx'
import { Button, EmptyState } from '../components/ui.tsx'

/** A link that leads nowhere says so, rather than dropping you on the home page. */
export function NotFound({ what = 'page' }: { what?: string }) {
  const nav = useNavigate()
  return (
    <Screen title="Not found">
      <EmptyState
        icon="search"
        title={`That ${what} is not here`}
        body={`The link may be old, or the ${what} was paused or removed.`}
        action={<Button onClick={() => nav('/')}>Explore what is free</Button>}
      />
    </Screen>
  )
}
