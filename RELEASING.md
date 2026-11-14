# Releasing Selfbrowse

How a new version gets to PyPI. Publishing is permanent: a version number can never be uploaded twice, even after a delete. So every release goes through a dry run first.

Releases use PyPI **Trusted Publishing**. GitHub proves to PyPI that the upload comes from this repository's `release` workflow, so there is no API token to create, store or leak. You do not need `twine upload` or a `~/.pypirc`.

## One-time setup

Do this once per index. Nothing here is stored in the repository.

1. **PyPI account.** Verified email, and two-factor authentication on.
2. **Register the publisher.** The project does not need to exist yet; use a *pending publisher*.
   - Real PyPI: <https://pypi.org/manage/account/publishing/> → "Add a new pending publisher".
   - TestPyPI (dry runs): <https://test.pypi.org/manage/account/publishing/>.
   - Fill in: project name `selfbrowse`, owner `rinshadkk`, repository `selfbrowse`, workflow `release.yml`, environment `pypi` (for TestPyPI: `testpypi`).
3. **GitHub environments.** Repository → Settings → Environments → create `pypi` and `testpypi`. On `pypi`, add yourself under "Required reviewers" so a release pauses for your approval before it uploads.

## Every release

1. **Check the state of the project.**
   ```bash
   git switch main && git pull
   .venv/bin/pytest -q                       # all green, and CI is green on main
   ```
2. **Pick the version** (`MAJOR.MINOR.PATCH`: fixes bump the last number, new features the middle one) and set it in one place, `src/selfbrowse/__init__.py`:
   ```python
   __version__ = "0.1.1"
   ```
3. **Update the docs that name a version or an install route** (README status line, `docs/getting-started.md`, the website's install box), and anything in `ROADMAP.md` that this release completes.
4. **Build and inspect locally** (optional but quick):
   ```bash
   rm -rf dist && .venv/bin/python -m build
   .venv/bin/twine check dist/*
   ```
5. **Commit and push** `Release 0.1.1`, and wait for CI to pass.
6. **Dry run on TestPyPI.** GitHub → Actions → *release* → "Run workflow". Then, in a clean environment:
   ```bash
   python3 -m venv /tmp/try && /tmp/try/bin/pip install \
     --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ selfbrowse
   /tmp/try/bin/selfbrowse --version
   ```
   A TestPyPI version also cannot be reused. If you re-run the dry run for the same version it will fail with "File already exists"; bump to the next patch number, or skip the dry run once it has passed.
7. **Publish.** GitHub → Releases → "Draft a new release" → create the tag `v0.1.1` (it must match `__version__`; the workflow stops if it does not) → write the notes → "Publish release". If you set required reviewers, approve the `pypi` deployment when it asks.
8. **Verify.** In a clean environment: `pip install selfbrowse==0.1.1` and `selfbrowse --version`.

## After the release

- Fix any docs that still say "install from source".
- If something is wrong with a published version, do not delete it. Publish a fixed version. A broken release can be marked "yanked" on its PyPI page so installers skip it.

## Before the first public release

Confirm that the name `selfbrowse` and the logo do not conflict with an existing trademark, and that nothing in the repository belongs to a current or former employer. These checks were set as a gate for the first release; record the outcome here when done.

## If an upload fails

| Error | Cause |
|---|---|
| `403 Forbidden` on a manual `twine upload` | Wrong username (it must be `__token__`), a TestPyPI token used on PyPI or the reverse, a project-scoped token for a project that does not exist yet, or an account without a verified email and two-factor authentication. Prefer the workflow, which uses no token. |
| `invalid-publisher` / "no matching publisher" in the workflow | The values registered on PyPI do not match: owner, repository, workflow file name (`release.yml`) and environment name must be identical. |
| `400 File already exists` | That version is already on the index. Bump the version. |
| "Tag ... does not match version" | The release tag differs from `__version__`. Fix whichever is wrong; for a tag, delete the release and tag and create them again. |

## Uploading by hand (fallback)

Only if the workflow is unavailable. Create an API token on the index, then:

```bash
.venv/bin/twine upload --repository testpypi dist/*     # dry run
.venv/bin/twine upload dist/*                           # real; username __token__, password is the token
```

Never put the token in a file inside the repository.
