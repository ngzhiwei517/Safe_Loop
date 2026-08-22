"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { createClient } from "../../lib/supabase/browser";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const { error: signInError } = await createClient().auth.signInWithPassword({ email, password });
    if (signInError) { setError(signInError.message); return; }
    router.push("/");
    router.refresh();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-6">
      <h1 className="text-3xl font-bold">SafeLoop AI</h1>
      <form className="space-y-4" onSubmit={submit}>
        <label className="block">Email<input className="mt-1 w-full rounded border p-3" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label className="block">Password<input className="mt-1 w-full rounded border p-3" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        {error && <p role="alert">{error}</p>}
        <button className="w-full rounded bg-orange-600 p-3 font-bold text-white" type="submit">Sign in</button>
      </form>
    </main>
  );
}
