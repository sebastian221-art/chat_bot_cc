// 📄 ARCHIVO: panel/components/ImageUpload.tsx
'use client'
import { useRef, useState } from 'react'
import { uploadImage } from '@/lib/api'
import { Upload, X, Loader2 } from 'lucide-react'

interface ImageUploadProps {
  value: string
  onChange: (url: string) => void
  label?: string
  accent?: 'indigo' | 'cyan' | 'amber' | 'violet' | 'emerald'
}

// Tailwind necesita ver las clases completas y literales en el código
// (no armadas con template strings) para poder generarlas — por eso
// este mapa, en vez de interpolar el color directamente.
const ACCENT_CLASSES: Record<string, string> = {
  indigo:  'hover:border-indigo-500 hover:text-indigo-400',
  cyan:    'hover:border-cyan-500 hover:text-cyan-400',
  amber:   'hover:border-amber-500 hover:text-amber-400',
  violet:  'hover:border-violet-500 hover:text-violet-400',
  emerald: 'hover:border-emerald-500 hover:text-emerald-400',
}

export default function ImageUpload({ value, onChange, label = 'Foto', accent = 'indigo' }: ImageUploadProps) {
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.startsWith('image/')) {
      alert('Solo se permiten imágenes (JPG, PNG, WEBP, GIF)')
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      alert('La imagen no puede pesar más de 8 MB')
      return
    }

    setUploading(true)
    try {
      const url = await uploadImage(file)
      onChange(url)
    } catch (err: any) {
      alert('Error al subir la imagen: ' + err.message)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  return (
    <div>
      <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
        {label} <span className="text-zinc-600 font-normal">(opcional)</span>
      </label>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFile}
        className="hidden"
      />

      {value ? (
        <div className="relative inline-block">
          <img
            src={value}
            alt="Vista previa"
            className="h-28 rounded-xl object-cover border border-zinc-700"
            onError={e => { (e.target as HTMLImageElement).style.opacity = '0.3' }}
          />
          <button
            type="button"
            onClick={() => onChange('')}
            className="absolute -top-2 -right-2 bg-zinc-900 border border-zinc-700 rounded-full p-1 text-zinc-400 hover:text-rose-400 hover:border-rose-800 transition-all"
          >
            <X size={12} />
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className={`ml-2 align-top mt-1 inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 px-2.5 py-1.5 rounded-lg transition-all disabled:opacity-50`}
          >
            {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            Cambiar
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className={`w-full flex items-center justify-center gap-2 border-2 border-dashed border-zinc-700 text-zinc-500 rounded-xl py-6 text-sm transition-all disabled:opacity-50 ${ACCENT_CLASSES[accent] || ACCENT_CLASSES.indigo}`}
        >
          {uploading ? (
            <><Loader2 size={16} className="animate-spin" /> Subiendo...</>
          ) : (
            <><Upload size={16} /> Toca para subir una foto</>
          )}
        </button>
      )}
    </div>
  )
}