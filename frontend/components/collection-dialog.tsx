// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useEffect, useId, useRef, type ReactNode } from "react";

export function CollectionDialog({
  title,
  children,
  onClose,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="collection-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="section-heading">
        <h2 id={titleId}>{title}</h2>
        <button
          type="button"
          className="inline-button"
          disabled={busy}
          onClick={onClose}
        >
          关闭
        </button>
      </div>
      {children}
    </dialog>
  );
}
