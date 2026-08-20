// 📄 ARCHIVO: panel/app/flujo-bot/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { getFlujoBot } from '@/lib/api'
import { Bot, MessageSquare, Search, Database, GitBranch, ChevronDown, ChevronRight, Layers, Zap, FileText } from 'lucide-react'

interface Intencion {
  nombre: string
  descripcion: string
  palabras_clave: string[]
  prompt_especifico: string
}
interface FlujoData {
  persona_base: string
  intenciones: Intencion[]
  busqueda_categoria: {
    palabras_intencion: string[]
    categorias: { nombre: string; terminos: string[] }[]
  }
  conteo_datos: Record<string, number>
}

const CONTEO_LABELS: Record<string, string> = {
  tiendas: 'Locales', base_conocimiento: 'Base de Conocimiento',
  eventos: 'Eventos', sorteos: 'Sorteos', promociones: 'Promociones',
}

export default function FlujoBotPage() {
  const [data, setData] = useState<FlujoData | null>(null)
  const [loading, setLoading] = useState(true)
  const [openIntent, setOpenIntent] = useState<string | null>(null)
  const [showPersona, setShowPersona] = useState(false)
  const [showCategorias, setShowCategorias] = useState(false)

  useEffect(() => {
    getFlujoBot().then(setData).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-8 text-zinc-500">Cargando el flujo del bot...</div>
  if (!data) return <div className="p-8 text-rose-400">No se pudo cargar el flujo.</div>

  return (
    <div className="p-6 max-w-4xl mx-auto pb-20">
      {/* Encabezado */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <GitBranch size={24} className="text-violet-400" />
          Flujo del Bot
        </h1>
        <p className="text-zinc-500 text-sm mt-1">
          Cómo Any decide, busca y responde — el recorrido real de cada mensaje. Solo lectura.
        </p>
      </div>

      {/* ── El recorrido de un mensaje ── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-wider text-zinc-500 font-semibold mb-3">El recorrido de un mensaje</h2>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-5 space-y-3">
          {[
            { icon: MessageSquare, color: 'text-sky-400', t: '1. Llega el mensaje', d: 'El cliente escribe por WhatsApp. Se guarda y se recupera el historial reciente de esa conversación.' },
            { icon: Zap, color: 'text-amber-400', t: '2. Se clasifica la intención', d: 'Según palabras clave, el mensaje se cataloga (saludo, horario, ubicación, domicilio, categoría, o general).' },
            { icon: GitBranch, color: 'text-violet-400', t: '3. Rutas directas primero', d: 'Antes de la IA, se revisan flujos determinísticos: ¿pide un número? ¿la cartelera de cine? ¿gestionar un domicilio? ¿una categoría de producto? Si aplica, se responde sin IA.' },
            { icon: Search, color: 'text-emerald-400', t: '4. Se busca la información', d: 'Si no aplicó una ruta directa, se buscan los locales y datos relevantes (RAG semántico + base de conocimiento) para dárselos a la IA.' },
            { icon: Bot, color: 'text-fuchsia-400', t: '5. La IA arma la respuesta', d: 'Con la personalidad base + el prompt de la intención + la información encontrada, el modelo redacta la respuesta.' },
            { icon: FileText, color: 'text-rose-400', t: '6. Se envía', d: 'Se limpian las marcas internas, se decide si adjuntar fotos, y se manda al cliente.' },
          ].map((paso, i) => (
            <div key={i} className="flex gap-3">
              <div className="shrink-0 mt-0.5"><paso.icon size={18} className={paso.color} /></div>
              <div>
                <p className="text-white text-sm font-medium">{paso.t}</p>
                <p className="text-zinc-500 text-xs mt-0.5 leading-relaxed">{paso.d}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Conteo de datos ── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-wider text-zinc-500 font-semibold mb-3">Información que alimenta al bot</h2>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {Object.entries(data.conteo_datos).map(([k, v]) => (
            <div key={k} className="bg-zinc-900 border border-zinc-800 rounded-xl p-3 text-center">
              <div className="text-2xl font-bold text-white">{v}</div>
              <div className="text-zinc-500 text-xs mt-0.5">{CONTEO_LABELS[k] || k}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Personalidad base ── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-wider text-zinc-500 font-semibold mb-3">Personalidad base (aplica a TODAS las respuestas)</h2>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
          <button onClick={() => setShowPersona(!showPersona)} className="w-full flex items-center justify-between p-4 hover:bg-zinc-850 transition-colors">
            <span className="flex items-center gap-2 text-white text-sm font-medium">
              <Layers size={16} className="text-violet-400" /> Reglas e identidad de Any
            </span>
            {showPersona ? <ChevronDown size={16} className="text-zinc-500" /> : <ChevronRight size={16} className="text-zinc-500" />}
          </button>
          {showPersona && (
            <pre className="px-4 pb-4 text-xs text-zinc-400 whitespace-pre-wrap font-mono leading-relaxed border-t border-zinc-800 pt-3">{data.persona_base}</pre>
          )}
        </div>
      </section>

      {/* ── Intenciones ── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-wider text-zinc-500 font-semibold mb-3">Tipos de respuesta (intenciones)</h2>
        <div className="space-y-3">
          {data.intenciones.map(intent => (
            <div key={intent.nombre} className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
              <button onClick={() => setOpenIntent(openIntent === intent.nombre ? null : intent.nombre)} className="w-full flex items-start justify-between p-4 hover:bg-zinc-850 transition-colors text-left">
                <div className="min-w-0">
                  <p className="text-white text-sm font-semibold capitalize">{intent.nombre.replace('_', ' ')}</p>
                  <p className="text-zinc-500 text-xs mt-1 leading-relaxed">{intent.descripcion}</p>
                </div>
                <div className="shrink-0 ml-3 mt-0.5">
                  {openIntent === intent.nombre ? <ChevronDown size={16} className="text-zinc-500" /> : <ChevronRight size={16} className="text-zinc-500" />}
                </div>
              </button>
              {openIntent === intent.nombre && (
                <div className="px-4 pb-4 border-t border-zinc-800 pt-3 space-y-3">
                  {intent.palabras_clave.length > 0 && (
                    <div>
                      <p className="text-zinc-500 text-xs font-semibold mb-1.5">Palabras que la activan:</p>
                      <div className="flex flex-wrap gap-1.5">
                        {intent.palabras_clave.map((k, i) => (
                          <span key={i} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded-md">{k}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {intent.prompt_especifico && (
                    <div>
                      <p className="text-zinc-500 text-xs font-semibold mb-1.5">Instrucción específica que se le da a la IA:</p>
                      <pre className="text-xs text-zinc-400 whitespace-pre-wrap font-mono leading-relaxed bg-zinc-950 rounded-lg p-3">{intent.prompt_especifico}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── Búsqueda justa por categoría ── */}
      <section>
        <h2 className="text-xs uppercase tracking-wider text-zinc-500 font-semibold mb-3">Búsqueda justa por categoría</h2>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4">
          <p className="text-zinc-400 text-xs leading-relaxed mb-3">
            Cuando alguien pregunta por un <strong className="text-zinc-200">tipo</strong> de producto (ej. "hamburguesas", "zapatos formales") sin nombrar una tienda, el bot lista <strong className="text-zinc-200">todos</strong> los locales de esa categoría — en orden alfabético neutral, sin destacar a ninguno, para garantizar equidad comercial.
          </p>
          <button onClick={() => setShowCategorias(!showCategorias)} className="flex items-center gap-2 text-xs text-violet-400 hover:text-violet-300 transition-colors">
            <Search size={14} />
            {showCategorias ? 'Ocultar' : 'Ver'} las {data.busqueda_categoria.categorias.length} categorías reconocidas
            {showCategorias ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          {showCategorias && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-3 pt-3 border-t border-zinc-800">
              {data.busqueda_categoria.categorias.map((cat, i) => (
                <div key={i} className="bg-zinc-950 rounded-lg px-3 py-2">
                  <p className="text-zinc-200 text-xs font-medium capitalize">{cat.nombre}</p>
                  <p className="text-zinc-600 text-[11px] mt-0.5">busca: {cat.terminos.join(', ')}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}