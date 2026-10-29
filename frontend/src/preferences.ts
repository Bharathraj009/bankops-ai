export function readPreference(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}
export function savePreference(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* The shell works when storage is restricted. */
  }
}
