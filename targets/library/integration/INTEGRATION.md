# SeekHarness integration

The current repository already recursively loads `targets/**/*.yaml`, but the legacy loader only allows: `id`, `category`, `format`, `tier`, `name`, `description`, `recommended_skills`, `target_code`, `test_code`, `objectives`, `limits`, and `scoring`. It therefore cannot directly materialize these multi-file target bundles.

Recommended integration sequence:

1. Add a Target Library storage record that stores metadata plus a server-side bundle path/version/hash.
2. At battle creation, resolve the selected target version and freeze its manifest hash into the battle record.
3. In the trusted backend, copy only `starter/` + `tests/visible/` into the fighter workspace.
4. Keep `tests/hidden/` and `reference/` outside all fighter workspaces.
5. For Builder/Breaker formats, snapshot only `handoff_allowlist` files, destroy the Builder workspace, then materialize the snapshot into the Breaker workspace.
6. Run hidden tests from the trusted verifier after the fighter phase completes.
7. Persist target id/version/hash and hidden-test result into the evidence package.

Do not place hidden tests or reference files into a Modal fighter sandbox simply because they exist in the source repository. They are evaluator-side material.
