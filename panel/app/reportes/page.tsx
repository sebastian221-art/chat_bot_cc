// 📄 ARCHIVO: panel/app/reportes/page.tsx
'use client'
import { useState } from 'react'
import { getAnalyticsSummary, getTopStores, getTopCategories, getOrderStats, runProfiling } from '@/lib/api'
import { FileText, Download, Sparkles, BarChart2, ShoppingBag, RefreshCw } from 'lucide-react'

type ReportType = 'semanal' | 'domicilios' | 'perfiles'

const REPORTS = [
  {
    id: 'semanal' as ReportType,
    icon: BarChart2,
    title: 'Reporte semanal',
    desc: 'Resumen de conversaciones, tiendas más consultadas y métricas del bot',
    color: 'indigo',
  },
  {
    id: 'domicilios' as ReportType,
    icon: ShoppingBag,
    title: 'Reporte de domicilios',
    desc: 'Pedidos, ingresos, locales top y calificaciones de la semana',
    color: 'emerald',
  },
  {
    id: 'perfiles' as ReportType,
    icon: Sparkles,
    title: 'Actualizar perfiles IA',
    desc: 'Ejecuta el job de perfilado para todos los usuarios con actividad reciente',
    color: 'violet',
  },
]

export default function ReportesPage() {
  const [generating, setGenerating] = useState<ReportType | null>(null)
  const [results, setResults]       = useState<Record<ReportType, string>>({} as any)

  const generateReport = async (type: ReportType) => {
    setGenerating(type)
    try {
      let content = ''

      if (type === 'semanal') {
        const [summary, stores, cats] = await Promise.all([
          getAnalyticsSummary(),
          getTopStores(),
          getTopCategories(),
        ])
        content = buildSemanalText(summary, stores, cats)
      }

      if (type === 'domicilios') {
        const stats = await getOrderStats()
        content = buildDomiciliosText(stats)
      }

      if (type === 'perfiles') {
        const result = await runProfiling()
        content = `✅ Job de perfilado completado\n\nPerfiles actualizados: ${result.profiles_updated}\nFecha: ${new Date().toLocaleString('es-CO')}`
      }

      setResults(prev => ({ ...prev, [type]: content }))
    } catch (e: any) {
      setResults(prev => ({ ...prev, [type]: `❌ Error: ${e.message}` }))
    } finally {
      setGenerating(null)
    }
  }

  const download = (type: ReportType) => {
    const text = results[type]
    if (!text) return
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `reporte_${type}_${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Reportes</h1>
        <p className="text-zinc-400 text-sm mt-1">Genera reportes del bot y los domicilios</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {REPORTS.map(({ id, icon: Icon, title, desc, color }) => (
          <div key={id} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 space-y-4">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-${color}-500/10`}>
              <Icon size={19} className={`text-${color}-400`} />
            </div>
            <div>
              <h3 className="text-white font-semibold">{title}</h3>
              <p className="text-zinc-500 text-xs mt-1 leading-relaxed">{desc}</p>
            </div>
            <button
              onClick={() => generateReport(id)}
              disabled={generating === id}
              className={`w-full py-2.5 rounded-xl text-xs font-medium transition-all disabled:opacity-50 bg-${color}-600 hover:bg-${color}-500 text-white flex items-center justify-center gap-2`}
            >
              {generating === id
                ? <><RefreshCw size={12} className="animate-spin" /> Generando...</>
                : <><FileText size={12} /> Generar</>
              }
            </button>

            {results[id] && (
              <div className="space-y-2">
                <pre className="text-xs text-zinc-400 bg-zinc-950 border border-zinc-800 rounded-xl p-3 overflow-y-auto max-h-48 whitespace-pre-wrap leading-relaxed">
                  {results[id]}
                </pre>
                <button
                  onClick={() => download(id)}
                  className="w-full flex items-center justify-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 py-2 rounded-xl transition-all"
                >
                  <Download size={12} /> Descargar .txt
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Helpers para construir el texto del reporte ───────────────────

function buildSemanalText(summary: any, stores: any[], cats: any[]): string {
  const now = new Date().toLocaleString('es-CO')
  return `REPORTE SEMANAL — CC El Puente
Generado: ${now}
${'─'.repeat(40)}

MENSAJES
  Esta semana: ${summary.messages_this_week}
  Semana anterior: ${summary.messages_last_week}
  Variación: ${summary.change_percentage > 0 ? '+' : ''}${summary.change_percentage}%
  Usuarios nuevos: ${summary.new_users_this_week}
  Tendencia: ${summary.trend === 'up' ? '📈 Subiendo' : '📉 Bajando'}

TOP TIENDAS MENCIONADAS
${stores.map((s: any, i: number) => `  ${i + 1}. ${s.store} — ${s.mentions} menciones`).join('\n') || '  Sin datos suficientes'}

CATEGORÍAS MÁS CONSULTADAS
${cats.slice(0, 5).map((c: any) => `  • ${c.category} — ${c.percentage}%`).join('\n') || '  Sin datos suficientes'}

${'─'.repeat(40)}
Generado automáticamente por Puente Bot Panel v2
`
}

function buildDomiciliosText(stats: any): string {
  const now = new Date().toLocaleString('es-CO')
  return `REPORTE DE DOMICILIOS — CC El Puente
Generado: ${now}
${'─'.repeat(40)}

HOY
  Pedidos totales: ${stats.total_today}
  Entregados:      ${stats.delivered_today}
  Pendientes ahora: ${stats.pending_now}
  Ingresos:        $${(stats.revenue_today || 0).toLocaleString('es-CO')} COP

TOP LOCALES (última semana)
${(stats.top_stores || []).map((s: any, i: number) => `  ${i + 1}. ${s.store} — ${s.total} pedidos`).join('\n') || '  Sin datos'}

CALIFICACIONES PROMEDIO
${(stats.avg_ratings || []).map((r: any) => `  • ${r.store}: ${'⭐'.repeat(Math.round(r.avg))} (${r.avg}/5)`).join('\n') || '  Sin calificaciones aún'}

${'─'.repeat(40)}
Generado automáticamente por Puente Bot Panel v2
`
}