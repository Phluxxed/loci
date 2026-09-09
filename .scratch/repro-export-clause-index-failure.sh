#!/usr/bin/env bash
# Repro for: `loci index` fails with GraphContractError
#   "Reference definition support does not match a current export"
# whenever a TypeScript file exports a declaration through an export CLAUSE
# (`export { name }` / `export { local as name }`) and another file imports it.
# Inline exports (`export function`, `export const`, `export default x`) pass.
# Usage: bash .scratch/repro-export-clause-index-failure.sh   (exit 0 = all cases pass)
set -u
D=$(mktemp -d)/repro; mkdir -p "$D"; cd "$D"; git init -q
fail=0
t(){ printf "$1" > a.ts; printf "$2" > b.ts; git add -A; git -c user.email=t@t -c user.name=t commit -qm x >/dev/null
     r=$(loci index . 2>&1 | tail -1)
     case "$r" in *Error*) echo "FAIL  $3"; echo "      $r"; fail=1;; *) echo "ok    $3";; esac; }
B="import { num } from './a'\nexport const x = num(1)\n"
t 'export function num(v: unknown): number { return Number(v) }\n' "$B" 'inline export function'
t 'export const num = (v: unknown): number => Number(v)\n' "$B" 'inline export const'
t 'function num(v: unknown): number { return Number(v) }\nexport default num\n' "import num from './a'\nexport const x = num(1)\n" 'export default identifier'
t 'function num(v: unknown): number { return Number(v) }\nexport { num }\n' "$B" 'export clause, same name        (expected to FAIL before fix)'
t 'function numHelper(v: unknown): number { return Number(v) }\nexport { numHelper as num }\n' "$B" 'export clause, aliased          (expected to FAIL before fix)'
exit $fail
