# Release checklist

1. Update `CHANGELOG.md` and the plugin's semantic version. Keep the v1 protocol
   marker, state directory and environment variables stable unless a migration
   is intentionally included. Published versions do not use local cachebusters.
2. Run `python3 tools/check.py` from a clean checkout. Review CI on macOS/Linux
   and each configured Python version. Do not claim a new CLI version works
   without a live compatibility check.
3. Run Gitleaks against the working tree and Git history. Review the actual
   tracked file list: no logs, credentials, local settings, personal absolute
   paths, raw real-user transcripts or bytecode. `.gitignore` does not remove
   files that were already committed.
4. Check the manifest, marketplace path, README installation instructions, docs
   links, license and release notes. Test marketplace installation from Git.
5. Confirm GitHub private vulnerability reporting is enabled and CI uses only
   read permissions, pinned actions, and no paid model credentials.
6. Tag the reviewed commit as `vX.Y.Z`, push the tag, and publish release notes
   describing compatibility and known limitations. GitHub's source archives are
   sufficient; do not attach local run directories or prebuilt opaque executables.
7. Open a fresh Codex Desktop task for the installed plugin. Optionally run a
   harmless live local smoke test; keep its private records out of the repository.

Use prerelease status for experimental 0.x releases until behavior and cross-CLI
compatibility have been established. Do not describe protocol consistency tests
as an independent security audit or guarantee of correct agent conclusions.
