// 📄 ARCHIVO: panel/app/analytics/page.tsx
'use client'
import { useEffect, useState } from 'react'
import {
  getAnalyticsSummary, getTopStores, getTopWords,
  getTopCategories, getAnalyticsHeatmap, getAnalyticsInsights,
} from '@/lib/api'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, RadarChart, PolarGrid, PolarAngleAxis, Radar
} from 'recharts'
import { TrendingUp, TrendingDown, Store, Hash, Tag, Lightbulb, AlertTriangle, Star, Clock } from 'lucide-react'

const DAYS_OPTIONS = [7, 14, 30]

export default function AnalyticsPage() {
  const [days, setDays]           = useState(7)
  const [summary, setSummary]     = useState<any>(null)
  const [topStores, setTopStores] = useState<any[]>([])
  const [topWords, setTopWords]   = useState<any[]>([])
  const [categories, setCategories] = useState<any[]>([])
  const [insights, setInsights]   = useState<any[]>([])
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getAnalyticsSummary(days),
      getTopStores(days),
      getTopWords(days),
      getTopCategories(days),
      getAnalyticsInsights(),
    ]).then(([s, st, tw, cats, ins]) => {
      setSummary(s)
      setTopStores(st)
      setTopWords(tw)
      setCategories(cats)
      setInsights(ins)
    }).catch(console.error)
    .finally(() => setLoading(false))
  }, [days])

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="text-zinc-500 animate-pulse">Cargando analytics...</div>
    </div>
  )

  const trend = summary?.trend === 'up'

  return (
    <div className="p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics</h1>
          <p className="text-zinc-400 text-sm mt-1">¿Qué está buscando la gente en el mall?</p>
        </div>
        {/* Selector de período */}
        <div className="flex gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1">
          {DAYS_OPTIONS.map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                days === d ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-white'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Acciones Sugeridas — el motor de recomendaciones */}
      <div>
        <h2 className="text-white font-semibold mb-1 flex items-center gap-2">
          <Lightbulb size={16} className="text-amber-400" /> Acciones Sugeridas
        </h2>
        <p className="text-zinc-500 text-xs mb-4">
          Lo que los datos dicen que deberías hacer — actualizado en tiempo real
        </p>
        {insights.length === 0 ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 text-center text-zinc-600 text-sm">
            Todavía no hay suficientes datos para generar recomendaciones. Vuelve cuando haya más actividad en el chat.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {insights.map((ins: any, i: number) => {
              const severityStyle: Record<string, { border: string; bg: string; icon: string; label: string }> = {
                up:     { border: 'border-emerald-900/50', bg: 'bg-emerald-950/30', icon: 'text-emerald-400', label: 'text-emerald-400' },
                down:   { border: 'border-rose-900/50',    bg: 'bg-rose-950/30',    icon: 'text-rose-400',    label: 'text-rose-400' },
                urgent: { border: 'border-red-800',        bg: 'bg-red-950/40',     icon: 'text-red-400',     label: 'text-red-400' },
                info:   { border: 'border-indigo-900/50',  bg: 'bg-indigo-950/30',  icon: 'text-indigo-400',  label: 'text-indigo-400' },
              }
              const style = severityStyle[ins.severity] || severityStyle.info
              const iconMap: Record<string, any> = { 'trending-up': TrendingUp, 'trending-down': TrendingDown, 'clock': Clock, 'alert-triangle': AlertTriangle, 'star': Star }
              const IconComp = iconMap[ins.icon] || Lightbulb

              return (
                <div key={i} className={`${style.bg} border ${style.border} rounded-2xl p-5`}>
                  <div className="flex items-start gap-3">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 bg-zinc-900/60`}>
                      <IconComp size={16} className={style.icon} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-semibold ${style.label}`}>{ins.title}</p>
                      <p className="text-zinc-400 text-xs mt-1.5 leading-relaxed">{ins.finding}</p>
                      <div className="mt-2.5 pt-2.5 border-t border-zinc-800/60">
                        <p className="text-zinc-300 text-xs leading-relaxed">
                          <span className="font-semibold">💡 Acción sugerida:</span> {ins.action}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Resumen de tendencia */}
      {summary && (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {[
            { label: 'Mensajes este período', value: summary.messages_this_week, icon: Hash, color: 'indigo' },
            { label: 'vs período anterior', value: `${summary.change_percentage > 0 ? '+' : ''}${summary.change_percentage}%`, icon: trend ? TrendingUp : TrendingDown, color: trend ? 'emerald' : 'red' },
            { label: 'Usuarios nuevos', value: summary.new_users_this_week, icon: Store, color: 'violet' },
            { label: 'Período anterior', value: summary.messages_last_week, icon: Tag, color: 'amber' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className={`bg-zinc-900 border border-zinc-800 rounded-2xl p-5`}>
              <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-3 bg-${color}-500/10`}>
                <Icon size={17} className={`text-${color}-400`} />
              </div>
              <p className="text-2xl font-bold text-white">{value}</p>
              <p className="text-zinc-500 text-xs mt-1">{label}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Top tiendas */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
          <h2 className="text-white font-semibold mb-1 flex items-center gap-2">
            <Store size={15} className="text-indigo-400" /> Top tiendas mencionadas
          </h2>
          <p className="text-zinc-500 text-xs mb-5">Cuántas veces se mencionó cada tienda</p>
          {topStores.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-8">Sin datos suficientes aún</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={topStores} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#71717a', fontSize: 11 }} />
                <YAxis dataKey="store" type="category" tick={{ fill: '#a1a1aa', fontSize: 11 }} width={90} />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }}
                  itemStyle={{ color: '#a5b4fc' }}
                />
                <Bar dataKey="mentions" fill="#6366f1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Categorías */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
          <h2 className="text-white font-semibold mb-1 flex items-center gap-2">
            <Tag size={15} className="text-emerald-400" /> Categorías más consultadas
          </h2>
          <p className="text-zinc-500 text-xs mb-5">Qué tipo de tiendas buscan más</p>
          {categories.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-8">Sin datos suficientes aún</p>
          ) : (
            <div className="space-y-3">
              {categories.slice(0, 7).map((c: any) => (
                <div key={c.category}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-zinc-300">{c.category}</span>
                    <span className="text-zinc-500">{c.mentions} ({c.percentage}%)</span>
                  </div>
                  <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full transition-all duration-700"
                      style={{ width: `${c.percentage}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Palabras más buscadas */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6">
        <h2 className="text-white font-semibold mb-1 flex items-center gap-2">
          <Hash size={15} className="text-violet-400" /> Palabras más frecuentes
        </h2>
        <p className="text-zinc-500 text-xs mb-5">
          Lo que más escribe la gente en el chat
        </p>
        {topWords.length === 0 ? (
          <p className="text-zinc-600 text-sm text-center py-8">Sin datos suficientes aún</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {topWords.map((w: any) => {
              const maxCount = topWords[0]?.count || 1
              const size = 12 + Math.round((w.count / maxCount) * 10)
              const opacity = 0.4 + (w.count / maxCount) * 0.6
              return (
                <span
                  key={w.word}
                  className="px-3 py-1.5 bg-violet-500/10 text-violet-300 border border-violet-500/20 rounded-full font-medium transition-all hover:bg-violet-500/20"
                  style={{ fontSize: `${size}px`, opacity }}
                >
                  {w.word}
                  <span className="ml-1 text-violet-500 text-xs">({w.count})</span>
                </span>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}