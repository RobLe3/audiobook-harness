# Contributing

Keep core production local-first and deterministic. Add tests for every quality
gate, keep fixtures original or public-domain, and do not add cloud fallbacks or
bundled third-party model weights. Update attribution, `models.lock.json`, and
`uv.lock` for any dependency or model change. Run the issue-specific local
verification profile plus the release profile before requesting a release.
Security-sensitive changes need a regression test for both the safe path and
the failed/blocked path; never include manuscripts, audio, credentials, or
voice assets in fixtures or reports.
