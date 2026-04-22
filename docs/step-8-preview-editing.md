# Step 8 - Editable Subtitle Preview

## What This Step Adds

The preview page is now a real subtitle editing workspace instead of a read-only summary.

Users can now:

- view every subtitle row
- edit `sourceText`
- edit `translatedText`
- search by source or translation text
- save the current edits
- retranslate a single subtitle row

## Main Files

- `src/components/SubtitlePreviewWorkspace.tsx`
- `src/components/SubtitleSearchToolbar.tsx`
- `src/components/EditableSubtitleRow.tsx`
- `src/App.tsx`

## How It Connects To ProjectState

The preview page reads from `ProjectState.segments` and writes back into the same state.

### Editing

When the user types into source or translation fields:

1. the row calls `onUpdateSegment(...)`
2. `App.tsx` updates the matching item inside `ProjectState.segments`
3. the preview instantly re-renders from the updated shared state

### Saving

Save does not create a separate file yet.

For Step 8, save means:

1. the current edited `ProjectState.segments` snapshot is marked as the saved version
2. the UI clears the unsaved-change warning
3. the preview records `lastSavedAt`

This keeps the current workflow simple while still giving the user a real save action before export.

### Single Retranslate

When the user clicks `Retranslate` on one row:

1. the current row is sent to the existing `/translate` backend route as a one-item list
2. only that returned segment is merged back into `ProjectState.segments`
3. other rows remain unchanged

If retranslating fails, the error is shown only on that row.

## Search

The preview page filters rows in real time.

- search checks both `sourceText` and `translatedText`
- filtering is local in the front end
- no backend request is needed

## Example Flow

See:

- `examples/preview-editing.example.json`

## Verification

```powershell
npm.cmd run lint
npm.cmd run build
```
