// 📄 ARCHIVO: panel/app/dashboard/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { getStats, StatsData } from '@/lib/api'
import StatCard from '@/components/StatCard'
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid
} from 'recharts'
import { MessageSquare, Users, TrendingUp, Store, RefreshCw } from 'lucide-react'

export default function DashboardPage() {
  const [data, setData]       = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const stats = await getStats()
      setData(stats)
      setLastUpdate(new Date())
    } catch (e) {
      console.error('Error cargando stats:', e)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  // Carga inicial
  useEffect(() => { load() }, [load])

  // Auto-refresh silencioso cada 60s
  useEffect(() => {
    const interval = setInterval(() => load(true), 60_000)
    return () => clearInterval(interval)
  }, [load])

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="text-zinc-500 animate-pulse">Cargando dashboard...</div>
    </div>
  )

  if (!data) return (
    <div className="text-red-400 text-sm p-6">
      No se pudo conectar al backend. ¿Está corriendo en localhost:8000?
    </div>
  )

  return (
    <div className="p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-zinc-400 text-sm mt-1">
            Resumen en tiempo real del chatbot
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500">
            Actualizado: {lastUpdate.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
          </span>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            Actualizar
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          label="Mensajes hoy"
          value={data.messages_today}
          icon={<MessageSquare size={18} />}
          color="indigo"
          delay={0}
        />
        <StatCard
          label="Esta semana"
          value={data.messages_this_week}
          icon={<TrendingUp size={18} />}
          color="emerald"
          delay={100}
        />
        <StatCard
          label="Usuarios únicos"
          value={data.unique_users}
          icon={<Users size={18} />}
          color="violet"
          delay={200}
        />
        <StatCard
          label="Tiendas"
          value={data.total_stores}
          icon={<Store size={18} />}
          color="amber"
          delay={300}
        />
      </div>

      {/* Gráfica mensajes 7 días */}
      <div className="bg-zinc-900 rounded-2xl p-6 border border-zinc-800">
        <h2 className="text-white font-semibold mb-1">Mensajes — últimos 7 días</h2>
        <p className="text-zinc-500 text-xs mb-5">Total de mensajes recibidos por día</p>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data.daily_chart}>
            <defs>
              <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="day"      tick={{ fill: '#71717a', fontSize: 11 }} />
            <YAxis allowDecimals={false} tick={{ fill: '#71717a', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }}
              labelStyle={{ color: '#fff' }}
              itemStyle={{ color: '#a5b4fc' }}
            />
            <Area type="monotone" dataKey="mensajes" stroke="#6366f1" strokeWidth={2} fill="url(#grad)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Gráfica horas pico */}
      <div className="bg-zinc-900 rounded-2xl p-6 border border-zinc-800">
        <h2 className="text-white font-semibold mb-1">Horas pico de hoy</h2>
        <p className="text-zinc-500 text-xs mb-5">¿A qué hora te escriben más?</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data.hourly_chart}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="hora" tick={{ fill: '#71717a', fontSize: 10 }} />
            <YAxis allowDecimals={false} tick={{ fill: '#71717a', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }}
              labelStyle={{ color: '#fff' }}
              itemStyle={{ color: '#34d399' }}
            />
            <Bar dataKey="mensajes" fill="#6366f1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}