"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import { btnPrimary } from "./ui";

type Phase = "idle" | "hashing" | "uploading" | "verifying" | "done" | "error";

async function sha256Hex(file: File) {
  const buf = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function putWithProgress(url: string, file: File, contentType: string, onProgress: (p: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", contentType);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`R2 yanıtı ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("Ağ hatası veya R2 CORS ayarı eksik"));
    xhr.send(file);
  });
}

export function VoiceoverUpload({ slug, kind, label }: { slug: string; kind: "doc" | "shorts"; label: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function upload(file: File) {
    setError(null);
    try {
      if (!/\.(mp3|wav)$/i.test(file.name)) throw new Error("Yalnızca .mp3 veya .wav");
      setPhase("hashing");
      const sha256 = await sha256Hex(file);
      const meta = { kind, filename: file.name, size: file.size, type: file.type || (file.name.endsWith(".wav") ? "audio/wav" : "audio/mpeg"), sha256 };
      const pre = await fetch(`/api/projects/${slug}/voiceover/presign`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(meta) });
      const p = await pre.json();
      if (!pre.ok) throw new Error(p.error ?? "Yükleme başlatılamadı");
      setPhase("uploading");
      await putWithProgress(p.url, file, p.contentType, setProgress);
      setPhase("verifying");
      const done = await fetch(`/api/projects/${slug}/voiceover/complete`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...meta, key: p.key }) });
      const d = await done.json();
      if (!done.ok) throw new Error(d.error ?? "Yükleme doğrulanamadı");
      setPhase("done");
      router.refresh();
    } catch (e) {
      setPhase("error");
      setError((e as Error).message);
    }
  }

  const busy = phase === "hashing" || phase === "uploading" || phase === "verifying";
  return (
    <div>
      <input ref={input} type="file" accept=".mp3,.wav,audio/mpeg,audio/wav" className="hidden" aria-label={`${label} dosyası`}
             onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      <button className={btnPrimary} disabled={busy} onClick={() => input.current?.click()}>
        <Upload size={15} /> {label} yükle (MP3/WAV)
      </button>
      {busy && (
        <div className="mt-2 text-xs text-zinc-400">
          {phase === "hashing" && "Dosya özeti hesaplanıyor…"}
          {phase === "uploading" && `R2'ye yükleniyor… %${Math.round(progress * 100)}`}
          {phase === "verifying" && "Doğrulanıyor…"}
          {phase === "uploading" && (
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/10"><div className="h-full bg-amber-400" style={{ width: `${progress * 100}%` }} /></div>
          )}
        </div>
      )}
      {phase === "done" && <p className="mt-2 text-xs text-emerald-300">Yüklendi. Analiz bulut işçisinde başlayacak.</p>}
      {error && <p role="alert" className="mt-2 text-xs text-rose-300">{error}</p>}
    </div>
  );
}
