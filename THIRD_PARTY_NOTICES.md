# Third-Party Notices

SpriteGameGen uses third-party software packages. Those packages remain subject
to their own copyright notices and license terms. This file does not replace the
license files distributed with those packages and is not a dependency-specific
license inventory.

## License review

The repository includes an offline policy check at
`scripts/check_dependency_licenses.py`. It reviews production dependencies from:

- installed Python distribution metadata, rooted at the installed
  `sprite-game-asset-tool` distribution; and
- `frontend/package-lock.json`, excluding entries marked as development-only.

Run the check from an environment where the backend project and its production
dependencies are installed:

```text
python scripts/check_dependency_licenses.py
```

The checker does not contact package registries or other network services. Its
output is a policy classification, not a substitute for reviewing the complete
license text, attribution requirements, notices, or dependency source archives.

Review and rerun the check whenever production dependencies or the npm lockfile
change. Investigate missing or unknown metadata against the license materials
shipped by the dependency. Any policy exception must be narrowly recorded in
the checker's reviewed exception table with the exact ecosystem, package,
version, declared license, and a reason. Revalidate existing exceptions when a
dependency version or its license metadata changes.

## Reviewed runtime exceptions

The offline policy records exact-version reviews for `certifi` (MPL-2.0 trust
data), `tqdm` (MPL-2.0 AND MIT, pulled by rembg), and `llvmlite` (Numba's
BSD-licensed LLVM binding whose wheel metadata omits a machine-readable license
expression). Any version or declared-license change invalidates the exception
and requires another review.
