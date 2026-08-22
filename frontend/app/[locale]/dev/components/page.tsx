import { notFound } from "next/navigation";

import { ComponentsGallery } from "../../../../components/dev/ComponentsGallery";

export default function ComponentsPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <ComponentsGallery />;
}
