"use client";

import {
  BellIcon,
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
  PlusIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import {
  approveDocument,
  listDocuments,
  retireDocument,
  uploadDocument,
  type CorpusDocument,
  type DocumentApprovalState,
} from "../../lib/documents";
import {
  defaultLocale,
  formatDate,
  formatNumber,
  isLocale,
  locales,
} from "../../lib/locales";
import { createClient } from "../../lib/supabase/browser";
import { AppShell } from "../ui/AppShell";
import { Banner } from "../ui/Banner";
import { PrimaryButton, SecondaryButton } from "../ui/Buttons";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Field } from "../ui/Field";
import { LanguageSwitch } from "../ui/LanguageSwitch";

const stateClasses: Record<DocumentApprovalState, string> = {
  pending: "bg-warningTint text-warning",
  approved: "bg-successTint text-successStrong",
  retired: "bg-surfaceSunken text-inkMuted",
};

const documentErrorKeys: Record<string, string> = {
  document_actor_forbidden: "error.document_actor_forbidden",
  document_not_found: "error.document_not_found",
  document_title_required: "error.document_title_required",
  document_ref_required: "error.document_ref_required",
  document_revision_required: "error.document_revision_required",
  document_file_required: "error.document_file_required",
  document_too_large: "error.document_too_large",
  document_type_not_allowed: "error.document_type_not_allowed",
  document_filename_invalid: "error.document_filename_invalid",
  document_type_mismatch: "error.document_type_mismatch",
  document_parse_failed: "error.document_parse_failed",
  document_text_empty: "error.document_text_empty",
  document_storage_not_configured: "error.document_storage_not_configured",
  document_storage_failed: "error.document_storage_failed",
};

export function DocumentsPage({ requestedLocale }: { requestedLocale: string }) {
  const t = useTranslations();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const [items, setItems] = useState<CorpusDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [failureKey, setFailureKey] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);

  const accessToken = useCallback(async () => {
    const { data: { session } } = await createClient().auth.getSession();
    if (!session) throw new Error("session_required");
    return session.access_token;
  }, []);

  const errorKey = useCallback((error: unknown) => {
    if (error instanceof ApiError) {
      return documentErrorKeys[error.body.detail.code] ?? "documents.error.generic";
    }
    return "documents.error.generic";
  }, []);

  const load = useCallback(async () => {
    setFailureKey(null);
    try {
      setItems(await listDocuments(await accessToken()));
    } catch (error) {
      setFailureKey(errorKey(error));
    } finally {
      setLoading(false);
    }
  }, [accessToken, errorKey]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const file = fields.get("file");
    if (!(file instanceof File) || file.size === 0) {
      setFailureKey("error.document_file_required");
      return;
    }
    setSaving(true);
    setFailureKey(null);
    try {
      await uploadDocument(
        {
          title: String(fields.get("title") ?? ""),
          docRef: String(fields.get("doc_ref") ?? ""),
          revision: String(fields.get("revision") ?? ""),
          effectiveFrom: String(fields.get("effective_from") ?? "") || undefined,
          file,
        },
        await accessToken(),
      );
      form.reset();
      setShowUpload(false);
      await load();
    } catch (error) {
      setFailureKey(errorKey(error));
    } finally {
      setSaving(false);
    }
  }

  async function changeApproval(document: CorpusDocument, action: "approve" | "retire") {
    setSavingId(document.id);
    setFailureKey(null);
    try {
      const token = await accessToken();
      if (action === "approve") {
        await approveDocument(document.id, token);
      } else {
        await retireDocument(document.id, token);
      }
      await load();
    } catch (error) {
      setFailureKey(errorKey(error));
    } finally {
      setSavingId(null);
    }
  }

  const navItems = [
    { href: `/${locale}/review`, label: t("review.nav.queue"), icon: <ClipboardDocumentListIcon className="h-5 w-5" /> },
    { href: `/${locale}/actions`, label: t("review.nav.actions"), icon: <WrenchScrewdriverIcon className="h-5 w-5" /> },
    { href: `/${locale}/documents`, label: t("review.nav.documents"), icon: <DocumentTextIcon className="h-5 w-5" /> },
    { href: `/${locale}/briefings`, label: t("review.nav.briefings"), icon: <BookOpenIcon className="h-5 w-5" /> },
    { href: `/${locale}/dashboard`, label: t("review.nav.dashboard"), icon: <ChartBarIcon className="h-5 w-5" /> },
  ];

  return (
    <AppShell
      title={t("documents.title")}
      inboxHref={`/${locale}/inbox`}
      inboxLabel={t("app.inbox")}
      inboxIcon={<BellIcon className="h-6 w-6" />}
      unreadCount={0}
      pollStatus
      showUrgentAlerts
      alertsHref={`/${locale}/alerts`}
      navItems={navItems}
      activeHref={`/${locale}/documents`}
      languageSwitch={(
        <LanguageSwitch
          current={locale}
          label={t("app.language")}
          options={[
            { value: locales[0], label: t("app.languageEnglish") },
            { value: locales[1], label: t("app.languageChinese") },
          ]}
        />
      )}
    >
      <section className="space-y-4 pb-6 pt-3">
        <div className="flex items-start gap-3">
          <p className="flex-1 text-sm leading-6 text-inkMuted">{t("documents.intro")}</p>
          <button
            aria-label={t("documents.add")}
            className="grid min-h-11 min-w-11 place-items-center rounded-control border border-border bg-surface text-primaryStrong"
            onClick={() => setShowUpload((current) => !current)}
            type="button"
          >
            <PlusIcon className="h-6 w-6" />
          </button>
        </div>

        {failureKey && (
          <Banner tone="warning" title={t("documents.error.title")} detail={t(failureKey)} />
        )}

        {showUpload && (
          <Card>
            <form className="space-y-4" onSubmit={(event) => void submitUpload(event)}>
              <h2 className="text-xl font-bold text-ink">{t("documents.upload.title")}</h2>
              <Field label={t("documents.upload.name")} name="title" required />
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("documents.upload.reference")} name="doc_ref" required />
                <Field label={t("documents.upload.revision")} name="revision" required />
              </div>
              <Field label={t("documents.upload.effectiveFrom")} name="effective_from" type="date" />
              <Field
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                label={t("documents.upload.file")}
                name="file"
                required
                type="file"
              />
              <p className="text-sm text-inkMuted">{t("documents.upload.help")}</p>
              <div className="grid grid-cols-2 gap-3">
                <SecondaryButton
                  label={t("documents.upload.cancel")}
                  onClick={() => setShowUpload(false)}
                  type="button"
                />
                <PrimaryButton
                  disabled={saving}
                  label={saving ? t("documents.upload.saving") : t("documents.upload.submit")}
                  type="submit"
                />
              </div>
            </form>
          </Card>
        )}

        {loading ? (
          <p className="py-8 text-center text-base text-inkMuted" role="status">
            {t("documents.loading")}
          </p>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<DocumentTextIcon className="h-8 w-8" />}
            title={t("documents.empty.title")}
            detail={t("documents.empty.detail")}
            action={<SecondaryButton label={t("documents.add")} onClick={() => setShowUpload(true)} />}
          />
        ) : (
          <div className="space-y-3">
            {items.map((document) => (
              <Card className="space-y-3" key={document.id}>
                <div className="flex items-start gap-3">
                  <h2 className="min-w-0 flex-1 text-lg font-bold text-ink">{document.title}</h2>
                  <span className={`shrink-0 rounded-chip px-3 py-1 text-xs font-bold ${stateClasses[document.approval_state]}`}>
                    {t(`documents.state.${document.approval_state}`)}
                  </span>
                </div>
                <p className="text-sm text-inkMuted">
                  {t("documents.meta", {
                    reference: document.doc_ref,
                    revision: document.revision,
                    effective: document.effective_from
                      ? formatDate(document.effective_from, locale)
                      : t("documents.effectiveMissing"),
                  })}
                </p>
                <p className="text-sm text-inkMuted">
                  {t("documents.citations", { count: formatNumber(document.cited_by_drafts, locale) })}
                </p>
                <p className="text-sm text-inkMuted">
                  {t("documents.chunks", { count: formatNumber(document.chunk_count, locale) })}
                </p>
                {document.approval_state === "approved" ? (
                  <SecondaryButton
                    disabled={savingId === document.id}
                    label={savingId === document.id ? t("documents.saving") : t("documents.retire", { revision: document.revision })}
                    onClick={() => void changeApproval(document, "retire")}
                  />
                ) : document.id === items.find((item) => item.approval_state !== "approved")?.id && !showUpload ? (
                  <PrimaryButton
                    disabled={savingId === document.id}
                    label={savingId === document.id ? t("documents.saving") : t("documents.approve", { revision: document.revision })}
                    onClick={() => void changeApproval(document, "approve")}
                  />
                ) : (
                  <SecondaryButton
                    disabled={savingId === document.id}
                    label={savingId === document.id ? t("documents.saving") : t("documents.approve", { revision: document.revision })}
                    onClick={() => void changeApproval(document, "approve")}
                  />
                )}
              </Card>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
