# Prompt Draft Versioned Compare Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a local-only versioned regenerate flow to `PromptDraftDialog` so users can compare old vs new prompt drafts side-by-side, inspect line diffs, choose which version to keep, and roll back across at most three local versions.

**Architecture:** Keep prompt generation on the existing backend regenerate API, but move all version/history management into frontend local storage. Refactor `PromptDraftDialog` into a small state machine with two primary modes: normal view and comparison view. Introduce version-aware storage helpers plus dedicated UI components for side-by-side comparison, diff rendering, and version history actions. Do not modify `PromptFineTuneDialog` in this work.

**Tech Stack:** React 19, TypeScript, Jest, localStorage, existing shadcn/ui dialog/button primitives

---

## UI Blueprint

### Normal Mode

```text
+----------------------------------------------------------------------------------+
| Prompt Draft                                                                     |
| Extract reusable rules from this conversation and generate a prompt draft        |
+----------------------------------------------------------------------------------+
| Model: [ Default Model v ]                                  [Regenerate] [Close] |
+----------------------------------------------------------------------------------+
|                                                                                  |
|  Title                                                                           |
|  产品协作助手                                                                    |
|                                                                                  |
|  Prompt                                                                          |
|  ------------------------------------------------------------------------------  |
|  你是产品协作助手，负责帮助我沉淀协作方式。                                      |
|                                                                                  |
|  ## 你的工作方式                                                                 |
|  - ...                                                                           |
|                                                                                  |
|  ## 处理任务时请遵循以下原则                                                     |
|  - ...                                                                           |
|                                                                                  |
|  ## 输出要求                                                                     |
|  - ...                                                                           |
|  ------------------------------------------------------------------------------  |
|                                                                                  |
+----------------------------------------------------------------------------------+
| Versions (max 3)                                                                 |
| [Current] V3  10:32  GPT-5.4     [View]                                          |
|          V2  10:26  GPT-5.4     [Rollback] [Compare to Current]                  |
|          V1  10:12  Default     [Rollback] [Compare to Current]                  |
+----------------------------------------------------------------------------------+
```

### Comparison Mode After Regenerate

```text
+--------------------------------------------------------------------------------------------------+
| Prompt Draft                                                   [Keep Old] [Use New as Current]   |
+--------------------------------------------------------------------------------------------------+
| Compare Result                                                                               |
| Changes: +8 / -3 / ~2                                                                        |
+--------------------------------------------------------------------------------------------------+
| Previous Version                                 | New Version                                  |
|--------------------------------------------------+----------------------------------------------|
| 你是产品协作助手，负责帮助我沉淀协作方式。       | 你是团队协作助手，负责沉淀协作规则。           |
|                                                  |                                              |
| ## 你的工作方式                                   | ## 你的工作方式                              |
| - 帮助用户总结                                    | - 主动提炼协作模式                           |
| - 给出建议                                        | - 输出可复用规则                             |
|                                                  | - 保持结构清晰                               |
|                                                  |                                              |
| ## 处理任务时请遵循以下原则                       | ## 处理任务时请遵循以下原则                  |
| - ...                                             | - ...                                        |
|                                                  |                                              |
| ## 输出要求                                       | ## 输出要求                                  |
| - ...                                             | - ...                                        |
|--------------------------------------------------+----------------------------------------------|
| Diff View                                                                                       |
| - 你是产品协作助手，负责帮助我沉淀协作方式。                                                    |
| + 你是团队协作助手，负责沉淀协作规则。                                                          |
|                                                                                                  |
| - 帮助用户总结                                                                                    |
| + 主动提炼协作模式                                                                                |
| + 输出可复用规则                                                                                  |
+--------------------------------------------------------------------------------------------------+
| Versions remain visible but disabled while a compare decision is pending                        |
+--------------------------------------------------------------------------------------------------+
```

### Interaction Rules

```text
Initial generate:
  no draft -> generate -> save V1 -> V1 becomes current

Regenerate:
  current Vn -> request candidate -> show compare(old=Vn, new=candidate)
    Keep Old -> discard candidate -> remain on Vn
    Use New -> store candidate as Vn+1 -> set current=Vn+1 -> trim to max 3 versions

Rollback:
  select any historical version Vi -> clone into a new version Vn+1(source=rollback)
  -> set current=Vn+1 -> trim to max 3 versions
```

### Scope Guardrails

- Do not touch `frontend/src/features/prompt-tune/components/PromptFineTuneDialog.tsx`
- Do not add backend persistence, DB schema, or new APIs
- Do not support arbitrary two-version compare in v1 beyond “compare to current”
- Do not support more than 3 locally stored versions

---

### Task 1: Redesign Prompt Draft Storage for Version History

**Files:**
- Modify: `frontend/src/features/prompt-draft/utils/promptDraftStorage.ts`
- Modify: `frontend/src/features/pet/utils/promptDraftStorage.ts`
- Test: `frontend/src/__tests__/features/prompt-draft/promptDraftStorage.test.ts`
- Test: `frontend/src/__tests__/features/pet/promptDraftStorage.test.ts`

**Step 1: Write the failing tests**

Add tests that define the new contract:

```ts
test('stores currentVersionId and up to three versions')
test('returns null and clears corrupted versioned payload')
test('promotes a chosen version to current without losing history')
test('trims oldest non-current version when more than three versions exist')
```

Use an explicit version payload shape:

```ts
{
  currentVersionId: 'v3',
  versions: [
    { id: 'v3', title: '...', prompt: '...', model: 'gpt-5.4', source: 'regenerate' },
    { id: 'v2', title: '...', prompt: '...', model: 'gpt-5.4', source: 'initial' },
    { id: 'v1', title: '...', prompt: '...', model: 'default-model', source: 'rollback' }
  ]
}
```

**Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- --runInBand src/__tests__/features/prompt-draft/promptDraftStorage.test.ts src/__tests__/features/pet/promptDraftStorage.test.ts
```

Expected: FAIL because storage currently only handles a single flat draft object.

**Step 3: Write minimal implementation**

Refactor storage into version-aware helpers:

- Keep `getPromptDraft` as a compatibility wrapper returning the current version for existing callers
- Add explicit helpers:
  - `savePromptDraftVersions`
  - `getPromptDraftVersions`
  - `appendPromptDraftVersion`
  - `setCurrentPromptDraftVersion`
  - `discardPromptDraftCandidate` if needed by dialog logic
- Ensure max history size is 3
- Preserve non-blocking localStorage behavior

**Step 4: Run tests to verify they pass**

Run the same Jest command.

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/features/prompt-draft/utils/promptDraftStorage.ts frontend/src/features/pet/utils/promptDraftStorage.ts frontend/src/__tests__/features/prompt-draft/promptDraftStorage.test.ts frontend/src/__tests__/features/pet/promptDraftStorage.test.ts
git commit -m "refactor(prompt-draft): add versioned local draft storage"
```

---

### Task 2: Extract Reusable Compare and History UI Components

**Files:**
- Create: `frontend/src/features/prompt-draft/components/PromptDraftComparisonPanel.tsx`
- Create: `frontend/src/features/prompt-draft/components/PromptDraftDiffView.tsx`
- Create: `frontend/src/features/prompt-draft/components/PromptDraftVersionList.tsx`
- Modify: `frontend/src/features/settings/components/prompt-fine-tune/PromptComparePanel.tsx`
- Test: `frontend/src/__tests__/features/prompt-draft/PromptDraftComparisonPanel.test.tsx`
- Test: `frontend/src/__tests__/features/prompt-draft/PromptDraftVersionList.test.tsx`

**Step 1: Write the failing tests**

Add component tests covering:

```ts
test('renders previous and new prompts side by side')
test('renders added and removed lines in diff view')
test('shows current badge only on current version')
test('disables rollback and compare actions while compare decision is pending')
```

**Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- --runInBand src/__tests__/features/prompt-draft/PromptDraftComparisonPanel.test.tsx src/__tests__/features/prompt-draft/PromptDraftVersionList.test.tsx
```

Expected: FAIL because the new components do not exist.

**Step 3: Write minimal implementation**

- Reuse the existing line-diff logic from `PromptComparePanel.tsx`, but move the diff utility into a small shared helper if needed
- `PromptDraftComparisonPanel` must render:
  - left column = previous version
  - right column = candidate version
  - diff summary counts
  - `Keep Old` and `Use New as Current` actions
- `PromptDraftVersionList` must render max 3 cards with:
  - version label
  - source
  - timestamp
  - current badge
  - rollback / compare buttons

**Step 4: Run tests to verify they pass**

Run the same Jest command.

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/features/prompt-draft/components/PromptDraftComparisonPanel.tsx frontend/src/features/prompt-draft/components/PromptDraftDiffView.tsx frontend/src/features/prompt-draft/components/PromptDraftVersionList.tsx frontend/src/features/settings/components/prompt-fine-tune/PromptComparePanel.tsx frontend/src/__tests__/features/prompt-draft/PromptDraftComparisonPanel.test.tsx frontend/src/__tests__/features/prompt-draft/PromptDraftVersionList.test.tsx
git commit -m "feat(prompt-draft): add comparison and version history components"
```

---

### Task 3: Refactor PromptDraftDialog into a Versioned State Machine

**Files:**
- Modify: `frontend/src/features/prompt-draft/components/PromptDraftDialog.tsx`
- Test: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`

**Step 1: Write the failing tests**

Extend `PromptDraftDialog.test.tsx` with these cases:

```ts
test('initial generation saves V1 as current version')
test('regenerate enters comparison mode instead of overwriting current prompt')
test('keep old discards candidate and preserves current version')
test('use new saves candidate and switches current version')
test('rollback clones historical version into a new current version')
test('history is trimmed to three versions after repeated accepts')
```

**Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend
npm test -- --runInBand src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected: FAIL because the dialog currently overwrites prompt state directly and has no compare/history state.

**Step 3: Write minimal implementation**

Refactor `PromptDraftDialog` state into:

- `currentVersionId`
- `versions`
- `pendingComparison`
- `isComparing`
- `selectedComparisonVersionId` for compare-to-current actions from history

Behavior to implement:

- Initial generate:
  - create V1
  - set current
- Regenerate:
  - preserve current version
  - request candidate
  - show comparison panel
  - do not store candidate permanently until accepted
- Keep Old:
  - discard candidate
  - exit compare mode
- Use New:
  - append candidate version
  - set current to candidate
  - trim to max 3 versions
- Rollback:
  - clone selected historical version into a new `rollback` version
  - set new clone as current
  - trim to max 3 versions

**Step 4: Run tests to verify they pass**

Run the same Jest command.

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/features/prompt-draft/components/PromptDraftDialog.tsx frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx
git commit -m "feat(prompt-draft): add versioned compare and rollback flow"
```

---

### Task 4: Add Translation Strings for Prompt Draft Compare and Version History

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN/pet.json`
- Modify: `frontend/src/i18n/locales/en/pet.json`

**Step 1: Write the failing test or assertion**

If there is no dedicated i18n test harness here, add shallow assertions in the affected component tests that the new keys are consumed, such as:

```ts
expect(screen.getByText('promptDraft.keepOld')).toBeInTheDocument()
expect(screen.getByText('promptDraft.useNew')).toBeInTheDocument()
```

**Step 2: Run tests to verify they fail**

Run the relevant dialog/component Jest suites.

Expected: FAIL because the translation keys do not exist yet or the UI does not render them.

**Step 3: Write minimal implementation**

Add keys for:

- `compareTitle`
- `keepOld`
- `useNew`
- `diffSummary`
- `versionsTitle`
- `currentVersion`
- `rollback`
- `compareToCurrent`
- `source.initial`
- `source.regenerate`
- `source.rollback`
- `pendingDecisionHint`

**Step 4: Run tests to verify they pass**

Run the related Jest suites again.

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN/pet.json frontend/src/i18n/locales/en/pet.json
git commit -m "feat(prompt-draft): add compare and version history copy"
```

---

### Task 5: Final Verification

**Files:**
- Test: `frontend/src/__tests__/features/prompt-draft/promptDraftStorage.test.ts`
- Test: `frontend/src/__tests__/features/pet/promptDraftStorage.test.ts`
- Test: `frontend/src/__tests__/features/prompt-draft/PromptDraftComparisonPanel.test.tsx`
- Test: `frontend/src/__tests__/features/prompt-draft/PromptDraftVersionList.test.tsx`
- Test: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`

**Step 1: Run focused frontend verification**

```bash
cd frontend
npm test -- --runInBand \
  src/__tests__/features/prompt-draft/promptDraftStorage.test.ts \
  src/__tests__/features/pet/promptDraftStorage.test.ts \
  src/__tests__/features/prompt-draft/PromptDraftComparisonPanel.test.tsx \
  src/__tests__/features/prompt-draft/PromptDraftVersionList.test.tsx \
  src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected: PASS

**Step 2: Run a broader prompt-draft test sweep**

```bash
cd frontend
npm test -- --runInBand src/__tests__/features/prompt-draft src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected: PASS

**Step 3: Manual QA checklist**

Validate in the browser:

- Generate first draft -> single version shown
- Regenerate -> compare mode appears, old prompt stays visible on left
- Keep Old -> candidate discarded
- Use New -> current version changes
- Rollback from V1/V2 -> new current version created
- History never exceeds 3 versions
- Refresh page -> local versions persist
- Open a different task -> no cross-task leakage

**Step 4: Final commit**

```bash
git add frontend/src/features/prompt-draft/components frontend/src/features/prompt-draft/utils/promptDraftStorage.ts frontend/src/features/pet/utils/promptDraftStorage.ts frontend/src/__tests__/features/prompt-draft frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx frontend/src/i18n/locales/zh-CN/pet.json frontend/src/i18n/locales/en/pet.json docs/plans/2026-03-29-prompt-draft-versioned-compare-implementation-plan.md
git commit -m "feat(prompt-draft): add local version compare and rollback"
```

---

## Notes for Implementation

- Keep the backend regenerate semantics exactly as implemented today
- Prefer extracting the line diff helper into a prompt-draft-local utility instead of coupling new UI to `PromptFineTuneDialog`
- Preserve all existing `data-testid` attributes and add new ones for:
  - `prompt-draft-keep-old-button`
  - `prompt-draft-use-new-button`
  - `prompt-draft-version-list`
  - `prompt-draft-version-card-<id>`
  - `prompt-draft-rollback-button-<id>`
  - `prompt-draft-compare-button-<id>`
- While compare decision is pending, history actions should be visually disabled to avoid ambiguous state transitions
- Do not store rejected regenerate candidates in history
