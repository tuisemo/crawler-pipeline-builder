export function getPublicAssetUrl(assetPath: string): string {
  const normalizedPath = assetPath.replace(/^\/+/, '')
  const basePath = window.location.pathname.endsWith('/')
    ? window.location.pathname
    : `${window.location.pathname}/`

  return new URL(normalizedPath, `${window.location.origin}${basePath}`).toString()
}
