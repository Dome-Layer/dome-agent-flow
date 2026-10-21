import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * House style: no em or en dashes anywhere in the tool's own text, visible copy and code comments
 * alike (the same rule and check as dome-website's src/houseStyle.test.ts). Use a comma, a colon,
 * a full stop or parentheses instead, and "N/A" for an empty value. Hyphens are fine.
 */
const ROOT = __dirname
const SKIP = new Set(['node_modules', 'out', 'coverage', 'public'])
const TEXT = /(\.(ts|tsx|js|mjs|cjs|css|json|jsonc)|^\.env\..*example)$/
const DASH = /[\u2013\u2014]/

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name.startsWith('.') && entry.isDirectory()) return []
    if (SKIP.has(entry.name) || entry.name === 'package-lock.json') return []
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return TEXT.test(entry.name) ? [path] : []
  })
}

describe('house style', () => {
  it('has no em or en dashes in the source', () => {
    const offenders = sourceFiles(ROOT).flatMap((file) =>
      readFileSync(file, 'utf8')
        .split('\n')
        .flatMap((line, i) => (DASH.test(line) ? [`${relative(ROOT, file)}:${i + 1}`] : [])),
    )
    expect(offenders).toEqual([])
  })
})
