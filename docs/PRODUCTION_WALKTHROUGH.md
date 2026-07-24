# Production walkthrough

The README animation is a readable representation of the local production
lifecycle. Its text frames live in `docs/assets/workflow-frames/`, and
`scripts/build_workflow_gif.sh` rebuilds the GIF using only local ImageMagick
and a local monospace font.

A chapter has eight gated stages:

1. Analyse the manuscript and create pronunciation, context, pause and
   performance plans.
2. Generate bounded lossless narration takes.
3. Verify alternatives and bind the selected take to its evidence.
4. Check text fidelity, timing, MFA alignment and short dialogue.
5. Confirm that all cue-sheet and evidence hashes form one release contract.
6. Assemble approved narration and optional locally supplied media.
7. Run post-mix fidelity, acoustic and regression checks.
8. Package M4A/MP3 plus a manifest into staging.

`stage` is intentionally not publication. The harness promotes a release only
when every chapter and the final series-level audit pass.
