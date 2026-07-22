// 📄 ARCHIVO: panel/app/conversaciones/page.tsx
'use client'
import { useEffect, useState, useCallback } from 'react'
import { getConversations, getConversationHistory, ConvUser } from '@/lib/api'
import { RefreshCw, User, Clock, MessageSquare, Sparkles } from 'lucide-react'

interface Message {
  role:      string
  message:   string
  timestamp: string
}

interface UserProfile {
  summary?:    string
  interests?:  string
  fav_stores?: string
  visit_freq?: string
}

interface ConvUserExt extends ConvUser {
  profile?: UserProfile
}

export default function ConversacionesPage() {
  const [users, setUsers]           = useState<ConvUserExt[]>([])
  const [selected, setSelected]     = useState<string | null>(null)
  const [history, setHistory]       = useState<Message[]>([])
  const [loadingH, setLoadingH]     = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdate, setLastUpdate] = useState(new Date())

  const loadUsers = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true)
    try {
      const data = await getConversations()
      // El backend devuelve array directo en /conversations
      setUsers(Array.isArray(data) ? data : [])
      setLastUpdate(new Date())
    } catch (e) {
      console.error(e)
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { loadUsers() }, [loadUsers])

  useEffect(() => {
    const interval = setInterval(() => loadUsers(true), 30_000)
    return () => clearInterval(interval)
  }, [loadUsers])

  const selectUser = async (phone: string) => {
    setSelected(phone)
    setLoadingH(true)
    setHistory([])
    try {
      const data = await getConversationHistory(phone)
      // El backend devuelve { phone, messages: [...] }
      const msgs = Array.isArray(data) ? data : (data?.messages ?? [])
      setHistory(msgs)
    } catch (e) {
      console.error(e)
      setHistory([])
    } finally {
      setLoadingH(false)
    }
  }

  const selectedUser = users.find(u => u.phone === selected)

  const freqColor = (freq?: string): string => {
    const map: Record<string, string> = {
      frecuente: 'text-emerald-400 bg-emerald-400/10',
      regular:   'text-indigo-400 bg-indigo-400/10',
      ocasional: 'text-zinc-400 bg-zinc-700',
    }
    return map[freq ?? 'ocasional'] ?? 'text-zinc-400 bg-zinc-700'
  }

  return (
    <div className="flex" style={{ height: '100vh', overflow: 'hidden' }}>

      {/* ── Lista de usuarios ── */}
      <div className="flex flex-col bg-zinc-950 border-r border-zinc-800" style={{ width: '300px', flexShrink: 0 }}>
        <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
          <div>
            <h2 className="text-white font-semibold">Conversaciones</h2>
            <p className="text-zinc-500 text-xs mt-0.5">{users.length} usuarios</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-600">
              {lastUpdate.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
            </span>
            <button
              onClick={() => loadUsers(true)}
              disabled={refreshing}
              className="p-1.5 text-zinc-500 hover:text-white rounded-lg hover:bg-zinc-800 transition-all disabled:opacity-40"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-zinc-800/60">
          {users.length === 0 ? (
            <div className="p-8 text-center text-zinc-600 text-sm">
              Sin conversaciones aún
            </div>
          ) : users.map(u => (
            <button
              key={u.phone}
              onClick={() => selectUser(u.phone)}
              className={`w-full text-left px-4 py-3.5 hover:bg-zinc-900 transition-colors ${
                selected === u.phone ? 'bg-zinc-900 border-l-2 border-indigo-500' : ''
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-full bg-indigo-600/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <User size={15} className="text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">{u.name || 'Sin nombre'}</p>
                  <p className="text-zinc-500 text-xs truncate">{u.phone}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-zinc-600 text-xs flex items-center gap-1">
                      <MessageSquare size={10} /> {u.total}
                    </span>
                    {u.profile?.visit_freq && (
                      <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqColor(u.profile.visit_freq)}`}>
                        {u.profile.visit_freq}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Panel derecho ── */}
      <div className="flex-1 flex flex-col bg-zinc-950 overflow-hidden">
        {selected ? (
          <>
            <div className="border-b border-zinc-800 p-4 flex-shrink-0">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-white font-semibold">{selectedUser?.name || 'Sin nombre'}</h3>
                  <p className="text-zinc-500 text-xs">{selected}</p>
                </div>
                <span className="text-zinc-600 text-xs flex items-center gap-1">
                  <Clock size={11} />
                  {lastUpdate.toLocaleDateString('es-CO')}
                </span>
              </div>

              {selectedUser?.profile?.summary && (
                <div className="mt-3 p-3 bg-indigo-950/40 border border-indigo-900/50 rounded-xl">
                  <p className="text-indigo-400 text-xs font-medium flex items-center gap-1.5 mb-1.5">
                    <Sparkles size={11} /> Perfil IA
                  </p>
                  <p className="text-zinc-300 text-xs leading-relaxed">{selectedUser.profile.summary}</p>
                  {selectedUser.profile.interests && (
                    <p className="text-zinc-500 text-xs mt-1.5">🎯 {selectedUser.profile.interests}</p>
                  )}
                  {selectedUser.profile.fav_stores && (
                    <p className="text-zinc-500 text-xs mt-0.5">🏪 {selectedUser.profile.fav_stores}</p>
                  )}
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-3">
              {loadingH ? (
                <div className="text-center text-zinc-600 py-12 animate-pulse">Cargando historial...</div>
              ) : history.length === 0 ? (
                <div className="text-center text-zinc-600 py-12">Sin mensajes aún</div>
              ) : (
                history.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[72%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-br-sm'
                        : 'bg-zinc-800 text-zinc-200 rounded-bl-sm'
                    }`}>
                      <p>{msg.message}</p>
                      <p className={`text-xs mt-1.5 ${msg.role === 'user' ? 'text-indigo-300' : 'text-zinc-500'}`}>
                        {new Date(msg.timestamp).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <MessageSquare size={40} className="text-zinc-700 mx-auto mb-3" />
              <p className="text-zinc-500 text-sm">Selecciona un usuario para ver su conversación</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}