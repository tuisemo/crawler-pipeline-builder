import { execFileSync } from 'node:child_process'
import { access, copyFile, cp, mkdir, rm } from 'node:fs/promises'
import { constants as fsConstants, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const packageRoot = join(scriptDir, '..')
const distDir = join(packageRoot, 'dist')
const manifestPath = join(packageRoot, 'manifest.json')
const releaseDir = join(packageRoot, 'release')
const unpackedDir = join(releaseDir, 'unpacked')
const zipPath = join(releaseDir, 'browser-bridge-extension.zip')
const mode = process.argv[2] ?? 'unpacked'

async function assertBuildArtifacts() {
  await access(distDir, fsConstants.R_OK)
  await access(manifestPath, fsConstants.R_OK)
}

async function prepareUnpackedExtension() {
  await rm(unpackedDir, { recursive: true, force: true })
  await mkdir(unpackedDir, { recursive: true })
  await copyFile(manifestPath, join(unpackedDir, 'manifest.json'))
  await cp(distDir, join(unpackedDir, 'dist'), { recursive: true })

  for (const entry of ['icons', '_locales']) {
    const source = join(packageRoot, entry)
    if (existsSync(source)) {
      await cp(source, join(unpackedDir, entry), { recursive: true })
    }
  }
}

function createZipArchive() {
  if (process.platform === 'win32') {
    const windowsShell = [
      'pwsh',
      join(process.env.ProgramFiles ?? 'C:\\Program Files', 'PowerShell', '7', 'pwsh.exe'),
      join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
      'powershell.exe',
    ].find((candidate) => {
      try {
        execFileSync(candidate, ['-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'], {
          stdio: 'ignore',
        })
        return true
      } catch {
        return false
      }
    })

    if (!windowsShell) {
      throw new Error('No PowerShell runtime found for ZIP packaging')
    }

    execFileSync(
      windowsShell,
      [
        '-NoProfile',
        '-Command',
        `Compress-Archive -Path (Join-Path '${unpackedDir}' '*') -DestinationPath '${zipPath}' -Force`,
      ],
      { stdio: 'inherit' },
    )
    return
  }

  execFileSync('zip', ['-qr', zipPath, '.'], {
    cwd: unpackedDir,
    stdio: 'inherit',
  })
}

const frontendPublicExtensionsDir = join(packageRoot, '..', '..', 'frontend', 'public', 'extensions')

async function copyToFrontend() {
  await rm(frontendPublicExtensionsDir, { recursive: true, force: true })
  await mkdir(frontendPublicExtensionsDir, { recursive: true })
  const targetDir = join(frontendPublicExtensionsDir, 'browser-bridge-extension')
  await cp(unpackedDir, targetDir, { recursive: true })
  console.log(`Copied unpacked extension to: ${targetDir}`)

  createZipArchive()
  const zipFileName = 'browser-bridge-extension.zip'
  await copyFile(zipPath, join(frontendPublicExtensionsDir, zipFileName))
  console.log(`Copied zip package to: ${join(frontendPublicExtensionsDir, zipFileName)}`)
}

async function main() {
  if (!['unpacked', 'zip', 'frontend'].includes(mode)) {
    throw new Error(`Unsupported packaging mode: ${mode}`)
  }

  await assertBuildArtifacts()
  await mkdir(releaseDir, { recursive: true })
  await rm(zipPath, { force: true })
  await prepareUnpackedExtension()

  if (mode === 'zip') {
    createZipArchive()
    console.log(`Created zip package: ${zipPath}`)
    return
  }

  console.log(`Created unpacked extension: ${unpackedDir}`)

  if (mode === 'frontend') {
    await copyToFrontend()
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  process.exit(1)
})
