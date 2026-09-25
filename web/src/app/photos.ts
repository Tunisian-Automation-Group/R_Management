// Getting a phone photograph down to something worth uploading.
//
// A phone produces 4 to 12 MB per picture and a card shows it at 400 px wide.
// Shrinking on the device keeps the upload quick on mobile data, keeps the
// store small, and turns HEIC (which only Safari can show) into JPEG, which
// everything can. App layer: it needs a canvas, so it never goes in domain/.
import { t } from '../i18n.ts'

/** Longest edge after shrinking (U-25): sharp on a desktop hero and a
 *  high-density phone, and a fraction of the camera's file. */
const MAX_EDGE = 2048
const QUALITY = 0.82

/** HEIC/HEIF: an iPhone's own format, which only Safari decodes. */
const isHeic = (f: File) => /image\/hei[cf]/i.test(f.type) || /\.hei[cf]$/i.test(f.name)

/** Thrown when a picture cannot be turned into something every browser shows. */
export class UnreadablePhoto extends Error {}

/**
 * The picture as a JPEG no larger than MAX_EDGE on its longest side, rotated
 * the way the camera meant it. Safari turns HEIC into JPEG here; a browser
 * that cannot read HEIC refuses it with a reason rather than upload a file
 * nobody else could see. Other undecodable files go up as they are, and the
 * server says what it thinks of them.
 */
export async function shrink(file: File): Promise<Blob> {
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    if (isHeic(file)) {
      throw new UnreadablePhoto(t('This browser cannot read HEIC photos. Take a screenshot of it, or on the iPhone set Camera → Formats → Most Compatible, and add it again.'))
    }
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
