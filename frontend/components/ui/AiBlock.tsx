import type { ReactNode } from "react";

type AiBlockProps = {
  marker: string;
  observedLabel: string;
  assumptionLabel: string;
  missingLabel: string;
  emptyLabel: string;
  observedFacts: string[];
  assumptions: string[];
  missingInformation: string[];
  validationTitle?: string;
  validationErrors?: string[];
  children?: ReactNode;
};

function ClaimList({ items, emptyLabel }: { items: string[]; emptyLabel: string }) {
  if (items.length === 0) {
    return <p className="mt-2 text-sm text-inkMuted">{emptyLabel}</p>;
  }
  return (
    <ul className="mt-2 list-disc space-y-2 pl-5 text-base leading-6">
      {items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
    </ul>
  );
}

export function AiBlock({
  marker,
  observedLabel,
  assumptionLabel,
  missingLabel,
  emptyLabel,
  observedFacts,
  assumptions,
  missingInformation,
  validationTitle,
  validationErrors = [],
  children,
}: AiBlockProps) {
  return (
    <section className="rounded-card border border-primary bg-primaryTint p-5" aria-label={marker}>
      <p className="text-sm font-bold text-primaryStrong">{marker}</p>
      <div className="mt-4">
        <h2 className="text-base font-bold text-ink">{observedLabel}</h2>
        <ClaimList items={observedFacts} emptyLabel={emptyLabel} />
      </div>
      <div className="mt-4 border-l-2 border-dashed border-border bg-surface/60 py-3 pl-4 pr-3 text-inkMuted">
        <h2 className="text-sm font-bold">{assumptionLabel}</h2>
        <div className="italic">
          <ClaimList items={assumptions} emptyLabel={emptyLabel} />
        </div>
      </div>
      <div className="mt-4 border-t border-border pt-4">
        <h2 className="text-sm font-bold text-ink">{missingLabel}</h2>
        <ClaimList items={missingInformation} emptyLabel={emptyLabel} />
      </div>
      {children}
      {validationTitle && validationErrors.length > 0 && (
        <div className="mt-4 rounded-control bg-warningTint p-3 text-warning">
          <p className="text-sm font-bold">{validationTitle}</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {validationErrors.map((error) => <li key={error}>{error}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
