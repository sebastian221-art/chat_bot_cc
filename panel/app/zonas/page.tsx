// 📄 ARCHIVO: panel/app/zonas/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getZones, createZone, updateZone, deleteZone, getZoneStats, Zone } from '@/lib/api'
import Modal from '@/components/Modal'
import { Plus, Pencil, Trash2, RefreshCw, MapPin, Copy, Check, QrCode, Flame } from 'lucide-react'

const FLOORS = ['Piso 1', 'Piso 2', 'Zona Burbuja']
const EMPTY: Zone = { code: '', floor: 'Piso 1', description: '' }

export default function ZonasPage() {
  const [zones, setZones]       = useState<(Zone & { _idx: number })[]>([])
  const [stats, setStats]       = useState<Record<string, number>>({})
  const [loading, setLoading]   = useState(true)
  const [modal, setModal]       = useState(false)
  const [editing, setEditing]   = useState<number | null>(null)
  const [form, setForm]         = useState<Zone>(EMPTY)
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [copiedId, setCopiedId] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [zonesData, statsData] = await Promise.all([getZones(), getZoneStats()])
      setZones(zonesData.map((z: Zone) => ({ ...z, _idx: z.id! })))
      const statsMap: Record<string, number> = {}
      statsData.forEach((s: any) => { statsMap[s.zone_code] = s.scans })
      setStats(statsMap)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openNew = () => { setForm(EMPTY); setEditing(null); setModal(true) }
  const openEdit = (z: Zone & { _idx: number }) => {
    setForm({ code: z.code, floor: z.floor, description: z.description })
    setEditing(z._idx)
    setModal(true)
  }
  const closeModal = () => setModal(false)

  const handleSave = async () => {
    if (!form.code.trim() || !form.floor.trim() || !form.description.trim()) {
      alert('Todos los campos son obligatorios')
      return
    }
    setSaving(true)
    try {
      if (editing !== null) {
        await updateZone(editing, form)
      } else {
        await createZone(form)
      }
      setModal(false)
      await load()
    } catch (err: any) {
      alert('Error al guardar: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar esta zona? El QR físico pegado en el mall dejará de funcionar.')) return
    setDeleting(id)
    try {
      await deleteZone(id)
      await load()
    } catch (err: any) {
      alert('Error al eliminar: ' + err.message)
    } finally {
      setDeleting(null)
    }
  }

  const copyLink = (id: number, link: string) => {
    navigator.clipboard.writeText(link)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  const field = (key: keyof Zone) => ({
    value: (form[key] as string) || '',
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value })),
  })

  const maxScans = Math.max(1, ...Object.values(stats))

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="text-2xl font-bold text-white">Navegación QR Indoor</h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            {zones.length} zonas configuradas — un QR físico por zona, pegado en el mall
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
            className="flex items-center gap-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium px-4 py-2 rounded-xl transition-all"
          >
            <Plus size={14} /> Nueva zona
          </button>
        </div>
      </div>

      {/* Tip */}
      <div className="mb-5 p-3 bg-cyan-950/30 border border-cyan-900/40 rounded-xl flex items-start gap-2.5">
        <QrCode size={15} className="text-cyan-400 flex-shrink-0 mt-0.5" />
        <p className="text-zinc-400 text-xs leading-relaxed">
          Cada zona genera un link único. Copia ese link y pégalo en cualquier generador de QR gratuito
          (por ejemplo, buscando "generador QR gratis") para imprimir el código y pegarlo físicamente en
          esa columna/pasillo del mall. Al escanearlo, el cliente ya sabe automáticamente dónde está.
        </p>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="text-center text-zinc-600 py-16 animate-pulse">Cargando zonas...</div>
      ) : zones.length === 0 ? (
        <div className="text-center text-zinc-600 py-16">
          <MapPin size={32} className="mx-auto mb-3 text-zinc-700" />
          Todavía no hay zonas — agrega la primera
        </div>
      ) : (
        <div className="space-y-3">
          {zones.map(z => {
            const scans = stats[z.code] || 0
            const heat = Math.round((scans / maxScans) * 100)
            return (
              <div key={z._idx} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-cyan-500/10 flex items-center justify-center flex-shrink-0">
                      <MapPin size={16} className="text-cyan-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-white font-semibold text-sm">Zona {z.code}</h3>
                        <span className="text-zinc-500 text-xs bg-zinc-800 px-2 py-0.5 rounded-full">{z.floor}</span>
                      </div>
                      <p className="text-zinc-400 text-xs mt-1">{z.description}</p>
                      <div className="flex items-center gap-2 mt-3">
                        <code className="text-xs text-cyan-300 bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-1 truncate max-w-xs">
                          {z.qr_link}
                        </code>
                        <button
                          onClick={() => copyLink(z._idx, z.qr_link || '')}
                          className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded-lg transition-all flex-shrink-0"
                        >
                          {copiedId === z._idx ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 flex-shrink-0">
                    <div className="text-right">
                      <p className="text-zinc-500 text-xs flex items-center gap-1 justify-end">
                        <Flame size={11} className={heat > 60 ? 'text-orange-400' : 'text-zinc-600'} /> Escaneos
                      </p>
                      <p className="text-white font-bold text-lg">{scans}</p>
                    </div>
                    <div className="flex gap-1.5">
                      <button
                        onClick={() => openEdit(z)}
                        className="p-2 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded-lg transition-all"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(z._idx)}
                        disabled={deleting === z._idx}
                        className="p-2 text-zinc-500 hover:text-rose-400 hover:bg-zinc-800 rounded-lg transition-all disabled:opacity-40"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Modal */}
      <Modal open={modal} title={editing !== null ? 'Editar zona' : 'Nueva zona'} onClose={closeModal} size="md">
        <div className="space-y-4">
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
              Código de zona * <span className="text-zinc-600 font-normal">(ej: A5, B2)</span>
            </label>
            <input className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500" placeholder="A5" {...field('code')} />
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Piso *</label>
            <select className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500" {...field('floor')}>
              {FLOORS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>

          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">
              Descripción de la ubicación *
            </label>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500 resize-none h-20"
              placeholder="ej: Ala norte, cerca de la fuente, frente a la entrada principal"
              {...field('description')}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-zinc-800">
          <button onClick={closeModal} className="px-4 py-2 text-sm text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all">
            Cancelar
          </button>
          <button onClick={handleSave} disabled={saving} className="px-4 py-2 text-sm text-white font-medium bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded-xl transition-all">
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </Modal>
    </div>
  )
}