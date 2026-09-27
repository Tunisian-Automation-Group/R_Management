// Runs before the first paint (a blocking script from our own origin, so the
// CSP's script-src 'self' allows it): sets data-theme so a dark phone never
// flashes a white page. theme.ts keeps it in step afterwards (UX-36).
;(function () {
  // Light unless the person chose Dark or System.
  var pref = 'light'
  try {
    pref = localStorage.getItem('cappy.theme.v1') || 'light'
  } catch (e) {}
  var dark = pref === 'dark' || (pref === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
})()
// Glass effects (VD-5, ADR 0014): 'lite' turns the blur off on hardware that
// would stutter. The person's own choice (You → Preferences) wins; otherwise
// the cheapest signals first: Save-Data, a small Android device, or an earlier
// slow scroll remembered on this device (theme.ts probes the first scroll).
;(function () {
  var mode = 'full'
  try {
    var chosen = localStorage.getItem('cappy.glass.v1')
    var probed = localStorage.getItem('cappy.glass.auto')
    var n = navigator
    var weak =
      (n.connection && n.connection.saveData) ||
      (/Android/i.test(n.userAgent) && ((n.deviceMemory && n.deviceMemory <= 4) || (n.hardwareConcurrency && n.hardwareConcurrency <= 4)))
    mode = chosen === 'full' || chosen === 'lite' ? chosen : weak || probed === 'lite' ? 'lite' : 'full'
  } catch (e) {}
  document.documentElement.dataset.glass = mode
})()
