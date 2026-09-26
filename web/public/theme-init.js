// Runs before the first paint (a blocking script from our own origin, so the
// CSP's script-src 'self' allows it): sets data-theme so a dark phone never
// flashes a white page. theme.ts keeps it in step afterwards (UX-36).
;(function () {
  var pref = 'system'
  try {
    pref = localStorage.getItem('cappy.theme.v1') || 'system'
  } catch (e) {}
  var dark = pref === 'dark' || (pref === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
})()
