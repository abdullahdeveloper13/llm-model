import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  const upstream = process.env.ASSISTANT_API_URL || "http://127.0.0.1:8000/assistant/command";
  try {
    const response = await fetch(upstream, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: String(body.text || "") }), cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ error: "The local assistant API is unavailable." }, { status: 503 });
  }
}
