import { useState } from "react";
import { ApiError } from "../../api/client";
import { Modal } from "../../components/ui/Modal";
import { TextField } from "../../components/ui/Field";
import { Button } from "../../components/ui/primitives";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (name: string, description: string | undefined, file: File) => Promise<void>;
}

export function DatasetUploadModal({ open, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a file to upload.");
      return;
    }

    setUploading(true);
    setError(null);
    try {
      await onSubmit(name, description || undefined, file);
      setName("");
      setDescription("");
      setFile(null);
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Could not upload dataset. Please try again.");
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Upload Dataset">
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && <p role="alert" className="rounded border border-danger-500/40 bg-danger-500/10 p-3 text-sm text-red-200">{error}</p>}
        <TextField label="Dataset name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Customer churn data" required />
        <TextArea label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does this dataset contain?" />
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ivory-100">CSV file</label>
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full rounded border border-surface-600 bg-surface-900 px-3.5 py-2 text-sm text-ivory-50 file:mr-4 file:rounded file:border-0 file:bg-surface-800 file:px-3 file:py-2 file:text-sm file:text-accent-400 hover:file:bg-surface-700"
            required
          />
          {file && <p className="mt-1 text-xs text-surface-400">Selected: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)</p>}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={uploading}>Cancel</Button>
          <Button type="submit" loading={uploading}>Upload</Button>
        </div>
      </form>
    </Modal>
  );
}

function TextArea({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void; placeholder?: string }) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-ivory-100">{label}</label>
      <textarea
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="block w-full rounded border border-surface-600 bg-surface-900 px-3.5 py-2 text-sm text-ivory-50 placeholder:text-surface-500 focus:border-accent-400 focus:outline-none min-h-24 resize-y"
      />
    </div>
  );
}
