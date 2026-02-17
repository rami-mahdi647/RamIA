#!/usr/bin/env node
import { execSync } from 'node:child_process'
import { writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

function cmd(c) {
  try {
    return execSync(c, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  } catch {
    return ''
  }
}

const commitHash = cmd('git rev-parse HEAD')
const shortCommit = cmd('git rev-parse --short HEAD')
const branch = cmd('git rev-parse --abbrev-ref HEAD')
const tag = cmd('git describe --tags --abbrev=0 2>/dev/null') || ''
const buildTimeIso = new Date().toISOString()

const content =
`/**
 * Archivo generado automáticamente. NO editar a mano.
 * Contiene metadata de la build.
 */
export interface BuildInfo {
  commitHash: string
  shortCommit: string
  branch: string
  tag: string | null
  buildTimeIso: string
}

export const BUILD_INFO: BuildInfo = {
  commitHash: '${commitHash}',
  shortCommit: '${shortCommit}',
  branch: '${branch}',
  tag: ${tag ? `'${tag}'` : 'null'},
  buildTimeIso: '${buildTimeIso}'
}
`

const __dirname = dirname(fileURLToPath(import.meta.url))
const outFile = resolve(__dirname, '../src/build-info.ts')

// Asegura carpeta src existente (debería existir)
mkdirSync(resolve(__dirname, '../src'), { recursive: true })
writeFileSync(outFile, content, 'utf8')
console.log('[gen-build-info] Archivo generado en', outFile)