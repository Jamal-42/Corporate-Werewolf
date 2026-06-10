import { NextResponse } from "next/server";
import { readdir } from "node:fs/promises";
import { resolve } from "node:path";
import { projectRoot } from "@/lib/server/game-runner";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const skillsDir = resolve(projectRoot, "skills", "versions");
    const entries = await readdir(skillsDir, { withFileTypes: true });
    const versions = entries
      .filter((e) => e.isDirectory())
      .map((e) => e.name)
      .sort();
    return NextResponse.json({ ok: true, versions });
  } catch {
    return NextResponse.json({ ok: true, versions: [] });
  }
}
