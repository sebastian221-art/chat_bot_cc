// 📄 ARCHIVO: panel/components/CineCartelera.tsx
'use client'
import { useEffect, useState } from 'react'
import { getCineFunciones, createCineFuncion, updateCineFuncion, deleteCineFuncion, CineFuncionPayload } from '@/lib/api'
import EntityPhotoGallery from '@/components/EntityPhotoGallery'
import { Plus, Pencil, Trash2, Film, X, Eye, EyeOff } from 'lucide-react'

interface Props {
  storeId: number
}

const EMPTY: Omit<CineFuncionPayload, 'store_id'> = {
  title: '', showtimes: '', description: '', is_premiere: false, active: true,
}

export default function CineCartelera({ storeId }: Props) {
  const [funciones, setFunciones] = useState<CineFuncionPayload[]>([])
  const [loading, setLoading]     = useState(false)
  const [editing, setEditing]     = useState<number | null>(null)
  const [showForm, setShowForm]   = useState(false)
  const [form, setForm]           = useState(EMPTY)
  const [saving, setSaving]       = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getCineFunciones(storeId)
      setFunciones(data)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [storeId])

  const openNew = () => { setForm(EMPTY); setEditing(null); setShowForm(true) }
  const openEdit = (f: CineFuncionPayload) => {
    setForm({ title: f.title, showtimes: f.showtimes, description: f.description, is_premiere: f.is_premiere, active: f.active })
    setEditing(f.id!)
    setShowForm(true)
  }
  const closeForm = () => setShowForm(false)

  const handleSave = async () => {
    if (!form.title.trim()) { alert('El título de la película es obligatorio'); return }
    setSaving(true)
    try {
      const payload: CineFuncionPayload = { ...form, store_id: storeId }
      if (editing !== null) await updateCineFuncion(editing, payload)
      else await createCineFuncion(payload)
      await load()
      closeForm()
    } catch (err: any) {
      alert('Error al guardar: ' + err.message)
    } finally { setSaving(false) }
  }

  const handleDelete = async (id: number, title: string) => {
    if (!confirm(`¿Quitar "${title}" de la cartelera?`)) return
    try {
      await deleteCineFuncion(id)
      await load()
    } catch (err: any) {
      alert('Error al eliminar: ' + err.message)
    }
  }

  // Activa/desactiva con un solo clic, sin tener que abrir el
  // formulario completo — reutiliza todos los demás datos de la
  // película tal como están, solo cambia el estado activo/inactivo.
  const handleToggleActive = async (f: CineFuncionPayload) => {
    try {
      const payload: CineFuncionPayload = {
        title: f.title, showtimes: f.showtimes, description: f.description,
        is_premiere: f.is_premiere, active: !f.active, store_id: storeId,
      }
      await updateCineFuncion(f.id!, payload)
      await load()
    } catch (err: any) {
      alert('Error al cambiar el estado: ' + err.message)
    }
  }

  return (
    <div className="bg-zinc-950 border border-amber-900/40 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-amber-400">
          <Film size={16} />
          <span className="text-sm font-semibold">Cartelera de Cine</span>
        </div>
        {!showForm && (
          <button
            onClick={openNew}
            className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300 transition-colors"
          >
            <Plus size={14} /> Agregar función
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-zinc-600 text-xs">Cargando cartelera...</p>
      ) : funciones.length === 0 && !showForm ? (
        <p className="text-zinc-600 text-xs">Sin películas cargadas todavía — agrega la cartelera de esta semana.</p>
      ) : (
        <div className="space-y-2 mb-3">
          {funciones.map(f => (
            <div key={f.id} className="flex items-start justify-between gap-2 bg-zinc-900 rounded-lg px-3 py-2">
              <div className="min-w-0">
                <p className="text-white text-sm font-medium flex items-center gap-1.5">
                  {f.title}
                  {f.is_premiere && <span className="text-[10px] bg-rose-500/20 text-rose-400 px-1.5 py-0.5 rounded-full font-semibold">ESTRENO</span>}
                  {!f.active && (
                    <button
                      onClick={() => handleToggleActive(f)}
                      className="text-[10px] bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 px-1.5 py-0.5 rounded-full font-semibold transition-colors"
                    >
                      Inactiva — click para activar
                    </button>
                  )}
                </p>
                {f.showtimes && <p className="text-zinc-500 text-xs mt-0.5">🕒 {f.showtimes}</p>}
                {f.description && <p className="text-zinc-600 text-xs mt-0.5 line-clamp-1">{f.description}</p>}
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => handleToggleActive(f)}
                  title={f.active ? 'Quitar de cartelera' : 'Poner en cartelera'}
                  className={f.active ? 'text-emerald-400 hover:text-emerald-300 transition-colors' : 'text-zinc-500 hover:text-zinc-300 transition-colors'}
                >
                  {f.active ? <Eye size={14} /> : <EyeOff size={14} />}
                </button>
                <button onClick={() => openEdit(f)} className="text-zinc-400 hover:text-white transition-colors">
                  <Pencil size={14} />
                </button>
                <button onClick={() => handleDelete(f.id!, f.title)} className="text-rose-400 hover:text-rose-300 transition-colors">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="bg-zinc-900 rounded-lg p-3 space-y-3 border border-zinc-800">
          <div className="flex items-center justify-between">
            <span className="text-zinc-400 text-xs font-semibold">
              {editing !== null ? 'Editar función' : 'Nueva función'}
            </span>
            <button onClick={closeForm} className="text-zinc-500 hover:text-white">
              <X size={14} />
            </button>
          </div>

          <div>
            <label className="text-zinc-500 text-xs block mb-1">Título de la película *</label>
            <input
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-white text-xs focus:outline-none focus:border-amber-500"
              placeholder="ej: Zootopia 2"
              value={form.title}
              onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
            />
          </div>

          <div>
            <label className="text-zinc-500 text-xs block mb-1">Horarios de función</label>
            <input
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-white text-xs focus:outline-none focus:border-amber-500"
              placeholder="ej: 2:00pm, 5:00pm, 8:00pm"
              value={form.showtimes}
              onChange={e => setForm(p => ({ ...p, showtimes: e.target.value }))}
            />
          </div>

          <div>
            <label className="text-zinc-500 text-xs block mb-1">Sinopsis / género / clasificación (opcional)</label>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-white text-xs focus:outline-none focus:border-amber-500 resize-none h-16"
              placeholder="ej: Animación, apta para todo público — 90 min"
              value={form.description}
              onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
            />
          </div>

          {editing !== null && (
            <div>
              <EntityPhotoGallery entityType="cine_funcion" entityId={editing} accent="amber" />
            </div>
          )}

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-1.5 text-zinc-300 text-xs">
              <input
                type="checkbox"
                checked={form.is_premiere}
                onChange={e => setForm(p => ({ ...p, is_premiere: e.target.checked }))}
                className="w-3.5 h-3.5 rounded border-zinc-700 bg-zinc-800"
              />
              Es estreno
            </label>
            <label className="flex items-center gap-1.5 text-zinc-300 text-xs">
              <input
                type="checkbox"
                checked={form.active}
                onChange={e => setForm(p => ({ ...p, active: e.target.checked }))}
                className="w-3.5 h-3.5 rounded border-zinc-700 bg-zinc-800"
              />
              En cartelera actualmente
            </label>
          </div>

          <div className="flex gap-2 justify-end pt-1">
            <button
              onClick={closeForm}
              className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 text-xs text-white font-medium bg-amber-600 hover:bg-amber-500 disabled:opacity-50 rounded-lg transition-all"
            >
              {saving ? 'Guardando...' : editing !== null ? 'Guardar' : 'Agregar'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}