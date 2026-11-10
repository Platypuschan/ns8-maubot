# UI dependency audit (2026-11-10)

Use the PR base/merge SHA for source provenance.

## Safe change

Constrain only `node-gyp/undici` to `^8.12.2` (lockfile: 8.12.4, previously
8.11.2). This remains within node-gyp's declared `^8.4.1` range and supports
our Node 24 builder. It removes eight Undici advisories from native-addon
build tooling, including TLS validation bypass, cross-origin cache disclosure,
SRI bypass and denial of service. It does not change browser dependencies.
A unit regression checks the scoped resolution and locked security floor.

Commands run before and after: `yarn install --immutable`, `yarn lint`,
`yarn build`, `yarn npm audit --all --recursive --json`.

| Audit result | Before | After |
| --- | ---: | ---: |
| Advisory records (excluding deprecations) | 13 | 5 |
| High-severity advisory records | 7 | 3 |
| All records (including deprecations) | 19 | 11 |

The remaining audit exit status is nonzero; this is not a clean security audit.

## Retained dependencies and warnings

Usage was checked in both `src/` and the installed ns8-ui-lib 2.2.1 sources
and distributed ESM bundle:

- `lottie-web-vue` is imported by `NsLottieAnimation`, consumed by
  `NsEmptyState`; the library's ESM bundle imports it. Keep its registration
  and the Lottie `eval` build warning. Removing it breaks library components.
- `vue-axios` supplies `this.axios`; ns8-ui-lib task/context/status methods
  call it. Keep the bridge and configured request timeout.
- `vue-debounce` supplies directives used by `NsDataTable` and
  `NsComboSearchBox`, including the compiled ESM templates. Keep it.
- No VueUse peer warning and no CJS/ESM warning reproduced.
- ESLint 6 is incompatible with the current Babel parser's peer range;
  ns8-ui-lib declares a build-only Rollup plugin without providing Rollup.
  Do not fake peer compatibility or install an unused build chain to hide
  these warnings. Coordinated lint-tooling upgrades are separate work.
- The CSS warning refers to `/cluster-admin/css/core.css`, intentionally
  supplied by the NS8 host at runtime.
- Minimatch is already 3.1.5; the recursive audit reports no Minimatch advisory.
  Do not force Minimatch 11 into consumers expecting its v3 API.

Remaining advisories: flatted 2.0.2 (DoS, prototype pollution), tmp 0.0.33
(symlink writes, path traversal), and Vue 2.7.16 (HTML-parser ReDoS).
Flatted/tmp come from ESLint 6's cache/interactive-editor tooling, not the
browser runtime. Fixing these by forcing different major/0.x API baselines is
not a demonstrably behavior-preserving patch; upgrade the lint stack together
in separate work. Vue 2 is a runtime risk and cannot be fixed here without the
explicitly excluded framework migration; avoid compiling untrusted templates.
Deprecation records for Carbon 10, Vue i18n 8 and old lint dependencies remain.
No warnings were suppressed and no tests were disabled.
