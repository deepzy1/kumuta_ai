import React, { useEffect, useState } from "react";
import { FileText, X } from "lucide-react";

export default function AttachmentPreview({
  file,
  disabled,
  onRemove,
  formatSize,
}) {
  const [preview, setPreview] = useState(null);
  useEffect(() => {
    if (!file.type.startsWith("image/")) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return (
    <div className="file-chip">
      {preview ? (
        <img src={preview} alt={`Preview of ${file.name}`} />
      ) : (
        <span className="attachment-icon pdf">
          <FileText size={25} />
        </span>
      )}
      <span>
        <strong>{file.name}</strong>
        <small>{formatSize(file.size)}</small>
      </span>
      <button
        type="button"
        className="icon"
        aria-label={`Remove ${file.name}`}
        disabled={disabled}
        onClick={onRemove}
      >
        <X size={15} />
      </button>
    </div>
  );
}
