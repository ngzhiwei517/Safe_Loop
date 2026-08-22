# Step 1.5 design QA

**Final result: passed**

## Comparison target

- Source visual truth: `docs/ui/A2_capture.png`, `docs/ui/A3_clarify.png`, `docs/ui/A5_confirm.png`, and `docs/ui/A6_done.png`, interpreted under `DESIGN.md` and the product invariants in `PRD.md`.
- Rendered implementation: production build at `/en/report/new` and `/en/report/SL-2026-00001`.
- Implementation screenshots: `docs/ui/implementation-A2-capture.png`, `docs/ui/implementation-A3-clarify.png`, `docs/ui/implementation-A5-confirm.png`, and `docs/ui/implementation-A6-done.png`.
- Full-view comparison evidence: `docs/ui/qa/qa-A2-comparison.png`, `docs/ui/qa/qa-A3-comparison.png`, `docs/ui/qa/qa-A5-comparison.png`, and `docs/ui/qa/qa-A6-comparison.png`.
- CSS viewport: 390 x 844 pixels at device scale factor 1.
- Source pixels: A2, A3, and A6 are 853 x 1844; A5 is 852 x 1846.
- Implementation pixels: 390 x 844 for every final capture.
- Density normalization: each source was downsampled to 390 x 844 with high-quality Lanczos resampling. The implementation was captured at its native CSS dimensions. The two 390 x 844 images were then placed side by side without additional scaling.
- States: empty capture; deterministic danger question with “No immediate danger” selected; populated review with a local photo preview; submitted confirmation.
- Focused-region comparison: no separate crop was needed because typography, icons, controls, selected state, status chip, and photo crops remained legible in the 1:1 implementation screenshots and the side-by-side comparisons.

## Findings

- No actionable P0, P1, or P2 differences remain.
- [P3] The reference quick-question screen places more empty space between the question card and primary action. The implementation retains the 56px primary action and token spacing required by DESIGN.md; the action remains thumb-reachable and the hierarchy is unchanged.
- [P3] The capture drop-zone border is lighter than it appears in the source image. It uses the required shared border token and remains visible against the sunken surface.

## Required fidelity surfaces

- Fonts and typography: hierarchy, weights, 16px minimum form text, line height, and wrapping are consistent across the four states. The app uses the existing design-system Arial fallback rather than introducing a new font dependency.
- Spacing and layout rhythm: the 390px layout preserves 20px page insets, 20px card radii, 44px minimum touch targets, 56px primary actions, clear card grouping, and a thumb-reachable submit action without horizontal overflow.
- Colors and visual tokens: all colours come from the shared token file. “Submitted” intentionally uses the DESIGN.md submitted colour rather than the green chip shown by the source mockup.
- Image quality and assets: Heroicons provide a consistent outline icon family. The selected local hazard photo uses an object-cover crop without stretching; upload and persistence are intentionally deferred to Step 1.6.
- Copy and content: all visible copy comes from the locale catalogues. The completion screen intentionally says the report is in the review queue and that a reviewer still needs to open it, preserving the urgent-alert acknowledgement invariant. It also does not claim that the local photo preview was saved.
- Interaction and accessibility: labels are associated with controls; back, camera, answer, disclosure, toggle, and primary actions meet the touch-target requirement; the selected answer and keyboard focus have visible token-based states.

## Comparison history

1. Initial comparison found P2 density drift: the camera target, danger-question card, and review photo strip were materially smaller than the source. The camera target was increased to 320px, the question card to 500px, and the review strip to a 5:4 split at 128px height. Post-fix evidence: all four `docs/ui/qa/qa-*-comparison.png` files.
2. Initial comparison found a P2 control mismatch: confidentiality rendered as a browser checkbox. It was replaced with a token-based switch while retaining native checkbox semantics. Post-fix evidence: `docs/ui/qa/qa-A5-comparison.png`.
3. Initial comparison found a P2 semantic-state mismatch: generated status classes used invalid camel-case CSS variable names. The state-machine generator now emits the token file's kebab-case names. Post-fix evidence: `docs/ui/qa/qa-A6-comparison.png`.
4. Initial comparison found a P2 product-truth issue in the source completion copy: it implied that the safety team had received the report and that the photo was saved. The implementation now states that the report is queued and still needs to be opened, and only claims the original report was saved. Post-fix evidence: `docs/ui/qa/qa-A6-comparison.png`.
5. A later selected-state capture exposed a P2 native black focus outline over the orange selected border. The answer controls now use the shared focus ring. Post-fix evidence: `docs/ui/implementation-A3-clarify.png`.

## Functional browser evidence

- Tested capture description entry, local photo selection, forward and back navigation, deterministic no-danger selection, location and activity entry, the review state, and the completion route.
- Verified the Simplified Chinese route renders translated catalogue copy.
- A fresh production tab reported zero console errors.
- Automated tests cover successful create-and-submit, failed submission with preserved input, and both locale renders.

## Implementation checklist

- [x] Match the three requested report-flow steps at 390px.
- [x] Preserve the PRD and DESIGN precedence where the mockup conflicts.
- [x] Verify primary interaction states and local photo preview.
- [x] Compare normalized source and implementation images side by side.
- [x] Re-run lint, strict type checking, tests, locale and token checks, and the production build.
