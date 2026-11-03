## Needs you

<!-- One line. What the human must do. Example: Merge, or request changes. -->

## Summary

<!-- 2 to 4 short sentences. What changes and why. -->

## Risk

<!-- One line, or: None known. -->

<details>
<summary>Agent detail</summary>

### Component(s)

<!-- Name the directories or services touched. -->

### Type

<!-- Keep the lines that apply. -->

- [ ] Added
- [ ] Changed
- [ ] Fixed
- [ ] Removed
- [ ] Plumbing (CI, shared config, docs)

### Changes

<!-- One bullet per notable change. -->

-

### Validation

<!-- List each check you ran and its result. -->

- [ ] Each statement reconciles `VERIFIED`, and none dropped to `REVIEW`
- [ ] `PYTHONPATH=. python tests/test_insights.py` prints `OK`
- [ ] The diff has no statement PDFs, real passwords or generated CSVs
- [ ] A bank change names the bank and where the sample came from
- [ ] CI is green

</details>
