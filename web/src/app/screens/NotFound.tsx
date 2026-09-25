import { Screen } from '../components/AppShell.tsx'
import { Button, EmptyState } from '../components/ui.tsx'
import { t } from '../../i18n.ts'

/** A link that leads nowhere says so, rather than dropping you on the home page. */
const COPY = {
  page: ['That page is not here', 'The link may be old, or the page was moved.'],
  listing: ['That listing is not here', 'The link may be old, or the listing was paused or removed.'],
  booking: ['That booking is not here', 'The link may be old, or the booking is not yours.'],
} as const

export function NotFound({ what = 'page' }: { what?: keyof typeof COPY }) {
  const [title, body] = COPY[what]
  return (
    <Screen title={t('Not found')}>
      <EmptyState
        icon="search"
        title={t(title)}
        body={t(body)}
        action={<Button to={'/'}>{t('Explore what is free')}</Button>}
      />
    </Screen>
  )
}
