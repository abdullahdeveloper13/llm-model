import { NextResponse } from "next/server";

export async function GET() {
  try {
    const base = (process.env.ASSISTANT_API_URL || "http://127.0.0.1:8000/assistant/command").replace(/\/assistant\/command$/, "");
    const response = await fetch(`${base}/assistant/context`, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ task_status: "OFFLINE" }, { status: 503 });
  }
}
