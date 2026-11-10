"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

import { Icon } from "@/components/icons";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  busyLabel?: string;
  busy?: boolean;
  tone?: "danger" | "default";
  onConfirm: () => void;
  onCancel: () => void;
};

/*
 * Native modal <dialog>: focus is contained and restored by the browser,
 * Escape cancels, and Cancel is the first (default-focused) action so a
 * destructive confirmation is never the accidental choice.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busyLabel = "Saving...",
  busy = false,
  tone = "danger",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) {
      return;
    }
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="gov-dialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) {
          onCancel();
        }
      }}
    >
      <div className="gov-dialog-body">
        <span
          className={`gov-dialog-icon${tone === "danger" ? " gov-dialog-icon--danger" : ""}`}
          aria-hidden="true"
        >
          <Icon name="alert-triangle" size={20} />
        </span>
        <div>
          <h2 id={titleId} className="gov-dialog-title">
            {title}
          </h2>
          <div id={descriptionId} className="gov-dialog-description">
            {description}
          </div>
        </div>
      </div>
      <div className="gov-dialog-actions">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="gov-button gov-button-secondary"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          aria-busy={busy || undefined}
          className={
            tone === "danger"
              ? "gov-button gov-button-danger-solid"
              : "gov-button gov-button-primary"
          }
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
