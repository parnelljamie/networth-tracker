// The Android app (docs/07-mobile.md "Android shell") injects `window.PassbookAndroid`. It isn't
// there in a desktop browser or the PC's window, so every use is feature-checked.

interface PassbookAndroidBridge {
  /** Opens the camera QR scanner; the result arrives through `window.onPassbookQrScanned`. */
  scanQrCode(): void
  /** Downloads the release APK and opens Android's installer; progress arrives through
   * `window.onPassbookUpdateStatus`. Missing in app versions from before Settings -> Updates. */
  installUpdate?(url: string, sha256: string | null): void
}

export interface AndroidUpdateStatus {
  /** "permission": Android opened "Install unknown apps" for Waymark; allow it, then try again. */
  state: "downloading" | "installing" | "permission" | "error"
  downloaded?: number
  total?: number
  error?: string
}

declare global {
  interface Window {
    PassbookAndroid?: PassbookAndroidBridge
    onPassbookQrScanned?: (text: string | null) => void
    onPassbookUpdateStatus?: (status: AndroidUpdateStatus) => void
  }
}

export function canScanQr(): boolean {
  return typeof window !== "undefined" && typeof window.PassbookAndroid?.scanQrCode === "function"
}

/** Resolves with the scanned text, or null if the scan was cancelled. */
export function scanQr(): Promise<string | null> {
  return new Promise((resolve) => {
    window.onPassbookQrScanned = (text) => {
      window.onPassbookQrScanned = undefined
      resolve(text || null)
    }
    window.PassbookAndroid?.scanQrCode()
  })
}

export function canInstallAndroidUpdate(): boolean {
  return typeof window !== "undefined" && typeof window.PassbookAndroid?.installUpdate === "function"
}

/** Starts the download; `onStatus` hears every step until the system installer opens. */
export function installAndroidUpdate(url: string, sha256: string | null, onStatus: (s: AndroidUpdateStatus) => void) {
  window.onPassbookUpdateStatus = onStatus
  window.PassbookAndroid?.installUpdate?.(url, sha256)
}
