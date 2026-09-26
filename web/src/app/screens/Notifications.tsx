import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { markNoticesRead, useNotices, type Notice } from '../../data/repo.ts'
import { Screen } from '../components/AppShell.tsx'
import { Button, EmptyState, Skeleton } from '../components/ui.tsx'
import { useNav } from '../nav.ts'
import { ago } from '../format.ts'
import { t } from '../../i18n.ts'

/** Everything Cappy told this person, newest first (U-22). Each opens the
 *  screen it is about; opening the list marks what is on it as read. */
export function Notifications() {
  const q = useNotices()
  const qc = useQueryClient()
  const nav = useNav()
  const unread = q.data?.unread ?? 0

  useEffect(() => {
    if (!unread) return
    const id = setTimeout(() => {
      void markNoticesRead()
        .catch(() => undefined) // an older backend: the count just stays
        .then(() => qc.invalidateQueries({ queryKey: ['notices'] }))
    }, 1500)
    return () => clearTimeout(id)
  }, [unread, qc])

  const open = (n: Notice) => {
    if (!n.link) return
    try {
      const u = new URL(n.link, window.location.origin)
      // Only inside the app: a link from the server never navigates away.
      if (u.origin === window.location.origin) nav(u.pathname + u.search)
    } catch {
      // Not a link we can follow.
    }
  }

  return (
    <Screen
      title={t('Notifications')}
      back="/"
      action={
        unread > 0 ? (
          <Button
            size="sm"
            variant="quiet"
            onClick={() => void markNoticesRead().then(() => qc.invalidateQueries({ queryKey: ['notices'] }))}
          >
            {t('Mark all as read')}
          </Button>
        ) : undefined
      }
    >
      {q.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : q.isError ? (
        <EmptyState
          icon="alert"
          title={t('Could not load notifications')}
          body={t('Check your connection and try again.')}
          action={<Button onClick={() => void q.refetch()}>{t('Try again')}</Button>}
        />
      ) : !q.data?.items.length ? (
        <EmptyState
          icon="bell"
          title={t('Nothing yet')}
          body={t('Requests, answers, messages and payouts show up here as they happen.')}
        />
      ) : (
        <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
          {q.data.items.map((n) => (
            <li key={n.id}>
              <button
                type="button"
                onClick={() => open(n)}
                className="flex w-full gap-3 py-4 text-left disabled:cursor-default"
                disabled={!n.link}
              >
                <span
                  aria-hidden="true"
                  className={`mt-2 h-2 w-2 shrink-0 rounded-full ${n.read ? 'bg-transparent' : 'bg-[var(--badge)]'}`}
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-body font-semibold">
                    {n.title}
                    {!n.read && <span className="sr-only"> ({t('unread')})</span>}
                  </span>
                  <span className="t-sm mt-0.5 block whitespace-pre-line text-[var(--ink-3)]">{n.body}</span>
                  <span className="t-sm mt-1 block text-[var(--ink-4)]">{ago(n.at)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Screen>
  )
}
