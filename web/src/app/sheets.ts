// The open sheets, top last, so Android's back button closes the top one
// first, as it closes a dialog in a native app (U-5).
const open: (() => void)[] = []

export function sheetOpened(close: () => void): () => void {
  open.push(close)
  return () => {
    const i = open.lastIndexOf(close)
    if (i >= 0) open.splice(i, 1)
  }
}

/** Closes the top sheet; false when there was none. */
export function closeTopSheet(): boolean {
  const close = open.at(-1)
  close?.()
  return Boolean(close)
}

/** Whether any sheet is open: a toast then shows at the top, not over its fields (V5-32). */
export const anySheetOpen = () => open.length > 0
