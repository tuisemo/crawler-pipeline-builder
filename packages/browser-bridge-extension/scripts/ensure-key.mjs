import { createHash, createPrivateKey, createPublicKey, generateKeyPairSync } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const packageRoot = join(scriptDir, '..')
const manifestPath = join(packageRoot, 'manifest.json')
const keysDir = join(packageRoot, 'keys')
const privateKeyPath = join(keysDir, 'browser-bridge-extension.pem')

function deriveExtensionId(publicKeyDer) {
  const digest = createHash('sha256').update(publicKeyDer).digest()
  const alphabet = 'abcdefghijklmnop'
  let extensionId = ''
  for (const byte of digest.subarray(0, 16)) {
    extensionId += alphabet[(byte >> 4) & 0x0f]
    extensionId += alphabet[byte & 0x0f]
  }
  return extensionId
}

function exportPublicKeyBase64(privateKeyPem) {
  const privateKey = createPrivateKey(privateKeyPem)
  const publicKeyDer = createPublicKey(privateKey).export({ type: 'spki', format: 'der' })
  return {
    manifestKey: Buffer.from(publicKeyDer).toString('base64'),
    extensionId: deriveExtensionId(Buffer.from(publicKeyDer)),
  }
}

async function ensurePrivateKey() {
  await mkdir(keysDir, { recursive: true })
  if (existsSync(privateKeyPath)) {
    return readFile(privateKeyPath, 'utf8')
  }

  const { privateKey } = generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: { type: 'spki', format: 'der' },
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
  })

  await writeFile(privateKeyPath, privateKey, { encoding: 'utf8', mode: 0o600 })
  return privateKey
}

async function syncManifestKey(manifestKey) {
  const raw = await readFile(manifestPath, 'utf8')
  const manifest = JSON.parse(raw)
  if (manifest.key === manifestKey) return false
  manifest.key = manifestKey
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
  return true
}

async function main() {
  const privateKeyPem = await ensurePrivateKey()
  const { manifestKey, extensionId } = await exportPublicKeyBase64(privateKeyPem)
  const changed = await syncManifestKey(manifestKey)
  console.log(`${changed ? 'Updated' : 'Kept'} manifest key; stable extension ID: ${extensionId}`)
  console.log(`Private key path: ${privateKeyPath}`)
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  process.exit(1)
})
