# flowforge JS Workspace

The JavaScript packages in this workspace are private, source-first workspace packages. Several package entrypoints intentionally export `src/*.ts` or `src/*.tsx` files so the monorepo test harness can typecheck and exercise the source directly.

Do not publish these packages to npm in their current shape. Before any package becomes public, add an explicit distribution build, point `main`/`types`/`exports` at generated `dist` artifacts, and update the private/source-first ratchet in `flowforge-integration-tests`.
