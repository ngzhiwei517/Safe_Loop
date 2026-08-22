import { apiFetch } from "./api";

export type DocumentApprovalState = "pending" | "approved" | "retired";

export type CorpusDocument = {
  id: string;
  title: string;
  doc_ref: string;
  revision: string;
  is_approved: boolean;
  approval_state: DocumentApprovalState;
  effective_from: string | null;
  approved_at: string | null;
  retired_at: string | null;
  chunk_count: number;
  cited_by_drafts: number;
  created_at: string;
};

export type DocumentUpload = {
  title: string;
  docRef: string;
  revision: string;
  effectiveFrom?: string;
  file: File;
};

export function listDocuments(accessToken: string): Promise<CorpusDocument[]> {
  return apiFetch<CorpusDocument[]>("/documents", accessToken);
}

export function uploadDocument(
  payload: DocumentUpload,
  accessToken: string,
): Promise<CorpusDocument> {
  const body = new FormData();
  body.set("title", payload.title);
  body.set("doc_ref", payload.docRef);
  body.set("revision", payload.revision);
  if (payload.effectiveFrom) body.set("effective_from", payload.effectiveFrom);
  body.set("file", payload.file);
  return apiFetch<CorpusDocument>("/documents", accessToken, { method: "POST", body });
}

export function approveDocument(documentId: string, accessToken: string): Promise<CorpusDocument> {
  return apiFetch<CorpusDocument>(`/documents/${documentId}/approve`, accessToken, { method: "POST" });
}

export function retireDocument(documentId: string, accessToken: string): Promise<CorpusDocument> {
  return apiFetch<CorpusDocument>(`/documents/${documentId}/retire`, accessToken, { method: "POST" });
}
