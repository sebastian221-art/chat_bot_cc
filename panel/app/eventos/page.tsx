// 📄 ARCHIVO: panel/app/eventos/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getEvents, createEvent, updateEvent, deleteEvent, EventPayload } from '@/lib/api'
import Modal from '@/components/Modal'
import { Plus, Pencil, Trash2, RefreshCw, Calendar } from 'lucide-react'

const EMPTY: EventPayload = { name: '', date: '', time: '', location: '', description: '' }

export default function EventosPage() {
  const [events, setEvents]     = useState<(EventPayload & { _idx: number })[]>([])
  const [loading, setLoading]   = useState(true)
  const [modal, setModal]       = useState(false)
  const [editing, setEditing]   = useState<number | null>(null)
  const [form, setForm]         = useState<EventPayload>(EMPTY)
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getEvents()
      setEvents(data.map((e: EventPayload, i: number) => ({ ...e, _idx: i })))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openNew = () => { setForm(EMPTY); setEditing(null); setModal(true) }
  const openEdit = (e: EventPayload & { _idx: number }) => {
    const { _idx, ...rest } = e
    setForm(rest); setEditing(_idx); setModal(true)
  }
  const closeModal = () => setModal(false)

  const handleSave = async () => {
    if (!form.name || !form.date) return alert('Nombre y fecha son requeridos')
    setSaving(true)
    try {
      if (editing !== null) await updateEvent(editing, form)
      else                  await createEvent(form)
      await load()
      closeModal()
    } catch (e: any) { alert('Error: ' + e.message) }
    finally { setSaving(false) }
  }

  const handleDelete = async (idx: number, name: string) => {
    if (!confirm(`¿Eliminar "${name}"?`)) return
    setDeleting(idx)
    try { await deleteEvent(idx); await load() }
    catch (e: any) { alert('Error: ' + e.message) }
    finally { setDeleting(null) }
  }

  const f = (key: keyof EventPayload) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value })),
  })

  const isUpcoming = (dateStr: string) => new Date(dateStr) >= new Date(new Date().toDateString())

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="text-2xl font-bold text-white">Eventos</h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            {events.length} eventos · {events.filter(e => isUpcoming(e.date)).length} próximos
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="p-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all"
          >
            <RefreshCw size={14} />
          </button>
          <button
            onClick={openNew}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium px-4 py-2 rounded-xl transition-all"
          >
            <Plus size={14} /> Nuevo evento
          </button>
        </div>
      </div>

      {/* Cards */}
      {loading ? (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(320px,1fr))' }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-44 bg-zinc-900 border border-zinc-800 rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-16 text-center">
          <Calendar size={40} className="text-zinc-700 mx-auto mb-3" />
          <p className="text-zinc-400 text-sm mb-1">No hay eventos programados</p>
          <p className="text-zinc-600 text-xs mb-5">
            Agrega el primero para que el bot lo informe a los visitantes
          </p>
          <button
            onClick={openNew}
            className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium px-4 py-2 rounded-xl transition-all"
          >
            <Plus size={13} /> Crear evento
          </button>
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(340px,1fr))' }}>
          {events.map((ev) => {
            const upcoming = isUpcoming(ev.date)
            return (
              <div
                key={ev._idx}
                className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 hover:border-zinc-700 transition-all relative overflow-hidden"
              >
                {/* Accent bar */}
                <div
                  className="absolute top-0 left-0 right-0 h-0.5"
                  style={{ background: upcoming ? 'linear-gradient(90deg,#10b981,#6366f1)' : '#3f3f46' }}
                />

                <div className="flex items-start justify-between mb-3">
                  <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold ${
                    upcoming
                      ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                      : 'bg-zinc-800 border-zinc-700 text-zinc-500'
                  }`}>
                    <Calendar size={11} />
                    {ev.date}
                    <span className={`ml-1 px-1.5 py-0.5 rounded-full text-xs ${
                      upcoming ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-700 text-zinc-500'
                    }`}>
                      {upcoming ? 'Próximo' : 'Pasado'}
                    </span>
                  </div>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => openEdit(ev)}
                      className="p-1.5 text-zinc-500 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all"
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      onClick={() => handleDelete(ev._idx, ev.name)}
                      disabled={deleting === ev._idx}
                      className="p-1.5 text-zinc-500 hover:text-red-400 bg-zinc-800 hover:bg-red-500/10 rounded-lg transition-all disabled:opacity-40"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>

                <h3 className="font-bold text-white text-sm leading-snug mb-2">{ev.name}</h3>

                {ev.description && (
                  <p className="text-zinc-500 text-xs leading-relaxed mb-3">{ev.description}</p>
                )}

                <div className="flex flex-wrap gap-3 pt-3 border-t border-zinc-800">
                  {ev.time && (
                    <span className="text-zinc-500 text-xs">🕐 {ev.time}</span>
                  )}
                  {ev.location && (
                    <span className="text-zinc-500 text-xs">📍 {ev.location}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Modal — open se pasa directamente, sin {modal && ...} */}
      <Modal
        open={modal}
        title={editing !== null ? 'Editar evento' : 'Nuevo evento'}
        onClose={closeModal}
      >
        <div className="space-y-4">

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Nombre del evento *</label>
            <input
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              placeholder="ej: Feria de Temporada"
              {...f('name')}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Fecha *</label>
              <input
                type="date"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
                {...f('date')}
              />
            </div>
            <div>
              <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Hora</label>
              <input
                className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
                placeholder="ej: 3:00pm - 7:00pm"
                {...f('time')}
              />
            </div>
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Lugar</label>
            <input
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              placeholder="ej: Plazoleta central, Piso 1"
              {...f('location')}
            />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Descripción</label>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 resize-none h-20"
              placeholder="Detalles del evento para informar a los visitantes..."
              {...f('description')}
            />
          </div>

        </div>

        <div className="flex gap-3 justify-end mt-6 pt-5 border-t border-zinc-800">
          <button
            onClick={closeModal}
            className="px-4 py-2 text-sm text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm text-white font-medium bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-xl transition-all"
          >
            {saving ? 'Guardando...' : editing !== null ? 'Guardar cambios' : 'Crear evento'}
          </button>
        </div>
      </Modal>

    </div>
  )
}