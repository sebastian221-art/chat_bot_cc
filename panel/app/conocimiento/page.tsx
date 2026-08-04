// 📄 ARCHIVO: panel/app/conocimiento/page.tsx
'use client'
import { useEffect, useState, useRef } from 'react'
import {
  getKnowledge, createKnowledge, updateKnowledge, deleteKnowledge,
  exportKnowledge, importKnowledge, KnowledgeEntry,
} from '@/lib/api'
import Modal from '@/components/Modal'
import { Plus, Pencil, Trash2, RefreshCw, BookOpen, Download, Upload, Search } from 'lucide-react'

const EMPTY: KnowledgeEntry = { title: '', content: '' }

export default function ConocimientoPage() {
  const [entries, setEntries]   = useState<(KnowledgeEntry & { _idx: number })[]>([])
  const [loading, setLoading]   = useState(true)
  const [search, setSearch]     = useState('')
  const [modal, setModal]       = useState(false)
  const [editing, setEditing]   = useState<number | null>(null)
  const [form, setForm]         = useState<KnowledgeEntry>(EMPTY)
  const [saving, setSaving]     = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [importing, setImporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getKnowledge()
      setEntries(data.map((e: KnowledgeEntry) => ({ ...e, _idx: e.id! })))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const result = await importKnowledge(file)
      alert(`Importación completa:\n✅ ${result.created} entradas nuevas\n🔄 ${result.updated} actualizadas\n⏭️ ${result.skipped} saltadas${result.errors?.length ? '\n\nAvisos:\n' + result.errors.join('\n') : ''}`)
      await load()
    } catch (err: any) {
      alert('Error al importar: ' + err.message)
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const filtered = entries.filter(e =>
    e.title.toLowerCase().includes(search.toLowerCase()) ||
    e.content.toLowerCase().includes(search.toLowerCase())
  )

  const openNew = () => { setForm(EMPTY); setEditing(null); setModal(true) }
  const openEdit = (e: KnowledgeEntry & { _idx: number }) => {
    setForm({ title: e.title, content: e.content })
    setEditing(e._idx)
    setModal(true)
  }
  const closeModal = () => setModal(false)

  const handleSave = async () => {
    if (!form.title.trim() || !form.content.trim()) {
      alert('Título y contenido son obligatorios')
      return
    }
    setSaving(true)
    try {
      if (editing !== null) {
        await updateKnowledge(editing, form)
      } else {
        await createKnowledge(form)
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
    if (!confirm('¿Eliminar esta entrada de la base de conocimiento?')) return
    setDeleting(id)
    try {
      await deleteKnowledge(id)
      await load()
    } catch (err: any) {
      alert('Error al eliminar: ' + err.message)
    } finally {
      setDeleting(null)
    }
  }

  const field = (key: keyof KnowledgeEntry) => ({
    value: (form[key] as string) || '',
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm(p => ({ ...p, [key]: e.target.value })),
  })

  return (
    <div className="p-8">

      {/* Header */}
      <div className="flex items-center justify-between mb-7">
        <div>
          <h1 className="text-2xl font-bold text-white">Base de Conocimiento</h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            {entries.length} entradas — texto libre que Any usa como contexto adicional al responder
          </p>
        </div>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleImportFile}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="flex items-center gap-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-sm font-medium px-3 py-2 rounded-lg transition-all"
          >
            <Upload size={14} /> {importing ? 'Importando...' : 'Importar CSV'}
          </button>
          <button
            onClick={() => exportKnowledge()}
            className="flex items-center gap-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 text-sm font-medium px-3 py-2 rounded-lg transition-all"
          >
            <Download size={14} /> Exportar CSV
          </button>
          <button
            onClick={load}
            className="p-2 text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-all"
          >
            <RefreshCw size={14} />
          </button>
          <button
            onClick={openNew}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-4 py-2 rounded-xl transition-all"
          >
            <Plus size={14} /> Nueva entrada
          </button>
        </div>
      </div>

      {/* Tip */}
      <div className="mb-5 p-3 bg-violet-950/30 border border-violet-900/40 rounded-xl flex items-start gap-2.5">
        <BookOpen size={15} className="text-violet-400 flex-shrink-0 mt-0.5" />
        <p className="text-zinc-400 text-xs leading-relaxed">
          Agrega aquí cualquier información que quieras que Any conozca y que no encaje en Locales o Eventos —
          políticas del mall, preguntas frecuentes, promociones especiales, protocolos, lo que sea. Cada entrada
          se indexa automáticamente y Any la usa como contexto al responder.
        </p>
      </div>

      {/* Buscador */}
      <div className="relative mb-5">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar en título o contenido..."
          className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500"
        />
      </div>

      {/* Lista */}
      {loading ? (
        <div className="text-center text-zinc-600 py-16 animate-pulse">Cargando base de conocimiento...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center text-zinc-600 py-16">
          <BookOpen size={32} className="mx-auto mb-3 text-zinc-700" />
          {entries.length === 0 ? 'Todavía no hay entradas — agrega la primera' : 'Sin resultados para esa búsqueda'}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map(e => (
            <div key={e._idx} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 hover:border-zinc-700 transition-all">
              <div className="flex items-start justify-between mb-2.5">
                <h3 className="text-white font-semibold text-sm pr-2">{e.title}</h3>
                <div className="flex gap-1.5 flex-shrink-0">
                  <button
                    onClick={() => openEdit(e)}
                    className="p-1.5 text-zinc-500 hover:text-white hover:bg-zinc-800 rounded-lg transition-all"
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={() => handleDelete(e._idx)}
                    disabled={deleting === e._idx}
                    className="p-1.5 text-zinc-500 hover:text-rose-400 hover:bg-zinc-800 rounded-lg transition-all disabled:opacity-40"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
              <p className="text-zinc-400 text-xs leading-relaxed line-clamp-4">{e.content}</p>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      <Modal open={modal} title={editing !== null ? 'Editar entrada' : 'Nueva entrada'} onClose={closeModal} size="md">
        <div className="space-y-4">
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Título *</label>
            <input
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-violet-500"
              placeholder="ej: Política de cambios y devoluciones"
              {...field('title')}
            />
          </div>
          <div>
            <label className="text-zinc-400 text-xs font-semibold block mb-1.5">Contenido *</label>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-violet-500 resize-none h-40"
              placeholder="Escribe aquí toda la información que Any debe saber sobre este tema..."
              {...field('content')}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-zinc-800">
          <button onClick={closeModal} className="px-4 py-2 text-sm text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-xl transition-all">
            Cancelar
          </button>
          <button onClick={handleSave} disabled={saving} className="px-4 py-2 text-sm text-white font-medium bg-violet-600 hover:bg-violet-500 disabled:opacity-50 rounded-xl transition-all">
            {saving ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </Modal>
    </div>
  )
}