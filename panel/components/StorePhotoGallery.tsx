// 📄 ARCHIVO: panel/components/StorePhotoGallery.tsx
'use client'
import { useEffect, useRef, useState } from 'react'
import { getStorePhotos, addStorePhoto, deleteStorePhoto, uploadImage, StorePhoto } from '@/lib/api'
import { Upload, X, Loader2, ImageOff } from 'lucide-react'

const LABELS = [
  { value: 'portada', label: '🏪 Portada / Local' },
  { value: 'carta', label: '📋 Carta' },
  { value: 'otra', label: '📷 Otra' },
]

export default function StorePhotoGallery({ storeId }: { storeId: number | null }) {
  const [photos, setPhotos] = useState<(StorePhoto & { id: number })[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [newLabel, setNewLabel] = useState('portada')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    if (!storeId) return
    setLoading(true)
    try {
      const data = await getStorePhotos(storeId)
      setPhotos(data)
    } catch {
      setPhotos([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [storeId])

  if (!storeId) {
    return (
      <div>
        <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Fotos</label>
        <p className="text-zinc-600 text-xs bg-zinc-800/50 border border-dashed border-zinc-700 rounded-xl px-3 py-4 text-center">
          Guarda el local primero — después podrás agregarle fotos aquí mismo
        </p>
      </div>
    )
  }

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) { alert('Solo se permiten imágenes'); return }
    if (file.size > 8 * 1024 * 1024) { alert('Máximo 8 MB por imagen'); return }

    setUploading(true)
    try {
      const url = await uploadImage(file)
      await addStorePhoto(storeId, { photo_url: url, label: newLabel })
      await load()
    } catch (err: any) {
      alert('Error al subir: ' + err.message)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDelete = async (photoId: number) => {
    if (!confirm('¿Eliminar esta foto?')) return
    try {
      await deleteStorePhoto(storeId, photoId)
      await load()
    } catch (err: any) {
      alert('Error al eliminar: ' + err.message)
    }
  }

  return (
    <div>
      <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
        Fotos <span className="text-zinc-600 font-normal">(puedes subir varias, cada una con su etiqueta)</span>
      </label>

      {loading ? (
        <p className="text-zinc-600 text-xs py-3">Cargando fotos...</p>
      ) : photos.length === 0 ? (
        <div className="flex items-center gap-2 text-zinc-600 text-xs bg-zinc-800/50 rounded-xl px-3 py-4 mb-3">
          <ImageOff size={14} /> Sin fotos todavía
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2 mb-3">
          {photos.map(p => (
            <div key={p.id} className="relative group">
              <img
                src={p.photo_url}
                alt={p.label}
                className="w-full h-20 object-cover rounded-lg border border-zinc-700"
                onError={e => { (e.target as HTMLImageElement).style.opacity = '0.2' }}
              />
              <span className="absolute bottom-1 left-1 text-[9px] bg-black/70 text-white px-1.5 py-0.5 rounded backdrop-blur-sm">
                {LABELS.find(l => l.value === p.label)?.label || p.label}
              </span>
              <button
                type="button"
                onClick={() => handleDelete(p.id)}
                className="absolute top-1 right-1 bg-black/70 text-zinc-300 hover:text-rose-400 rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Agregar nueva foto: primero la etiqueta, luego el archivo */}
      <div className="flex gap-2">
        <select
          value={newLabel}
          onChange={e => setNewLabel(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 rounded-xl px-2 py-2 text-white text-xs focus:outline-none focus:border-indigo-500"
        >
          {LABELS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
        </select>
        <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex-1 flex items-center justify-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl px-3 py-2 transition-all disabled:opacity-50"
        >
          {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
          {uploading ? 'Subiendo...' : `Agregar foto de ${LABELS.find(l => l.value === newLabel)?.label.split(' ').slice(1).join(' ')}`}
        </button>
      </div>
    </div>
  )
}