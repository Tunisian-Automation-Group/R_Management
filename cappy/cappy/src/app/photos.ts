// Getting a phone photograph down to something worth uploading.
//
// A phone produces 4 to 12 MB per picture and a card shows it at 400 px wide.
// Shrinking on the device keeps the upload quick on mobile data, keeps the
// store small, and turns HEIC (which only Safari can show) into JPEG, which
// everything can. App layer: it needs a canvas, so it never goes in domain/.

/** Longest edge after shrinking. Enough for a full-width hero on a phone. */
const MAX_EDGE = 1600
const QUALITY = 0.82

/**
 * The picture as a JPEG no larger than MAX_EDGE on its longest side, rotated
 * the way the camera meant it. Falls back to the original file when the
 * browser cannot decode it, and lets the server say what it thinks of that.
 */
export async function shrink(file: File): Promise<Blob> {
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    return file
  }
  try {
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    const w = Math.max(1, Math.round(bitmap.width * scale))
    const h = Math.max(1, Math.round(bitmap.height * scale))
    if (scale === 1 && file.type === 'image/jpeg' && file.size < 600_000) return file

    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    // A transparent PNG on a white card should stay white, not turn black.
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, w, h)
    ctx.drawImage(bitmap, 0, 0, w, h)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', QUALITY))
    return blob ?? file
  } finally {
    bitmap.close()
  }
}

/** The most photographs a listing takes. Matches the server's limit. */
export const MAX_PHOTOS = 8
