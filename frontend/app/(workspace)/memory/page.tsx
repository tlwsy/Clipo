// SPDX-License-Identifier: AGPL-3.0-or-later
"use client";
import { useRouter } from "next/navigation";
import { MemoryGallery } from "@/components/memory-gallery";

export default function MemoryPage() {
  const router = useRouter();
  return <MemoryGallery onClose={() => router.push("/", { scroll: false })} />;
}
