import { useState } from "react";

// Small inline text editor: Enter = save, Escape = cancel.
export default function InlineEdit({ initialValue, onSave, onCancel, maxLength = 200, label = "Name" }) {
  const [value, setValue] = useState(initialValue);
  const [saving, setSaving] = useState(false);

  async function save() {
    const next = value.trim();
    if (!next || saving) return;
    if (next === initialValue) {
      onCancel();
      return;
    }
    setSaving(true);
    try {
      await onSave(next);
    } finally {
      setSaving(false);
    }
  }

  return (
    <span className="inline-edit">
      <input
        autoFocus
        aria-label={label}
        value={value}
        maxLength={maxLength}
        disabled={saving}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") onCancel();
        }}
      />
      <button type="button" className="btn-link" onClick={save} disabled={saving || !value.trim()}>
        {saving ? "Saving…" : "Save"}
      </button>
      <button type="button" className="btn-link btn-link--muted" onClick={onCancel} disabled={saving}>
        Cancel
      </button>
    </span>
  );
}
