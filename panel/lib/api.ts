// 📄 ARCHIVO: panel/lib/api.ts  ← REEMPLAZA EL TUYO
// CAMBIOS: header Authorization automático en todas las peticiones
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getToken(): string {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem('cc_panel_token') || ''
}

async function req(path: string, options?: RequestInit) {
  const token = getToken()
  const res = await fetch(`${API}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: 'no-store',
    ...options,
  })
  if (!res.ok) {
    // Si el backend responde 401, limpiar sesión y redirigir
    if (res.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('cc_panel_token')
      localStorage.removeItem('cc_panel_user')
      window.location.href = '/login'
      return
    }
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// ── Helpers para archivos (import/export CSV) ──────────────────────
async function uploadFile(path: string, file: File) {
  const token = getToken()
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    // OJO: no ponemos Content-Type — el navegador lo arma solo con el
    // boundary correcto para multipart/form-data
    body: formData,
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

async function downloadFile(path: string, filename: string) {
  const token = getToken()
  const res = await fetch(`${API}${path}`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

// ── Auth ─────────────────────────────────────────────────────────
export const login     = (username: string, password: string) =>
  req('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })

export const getMe     = () => req('/auth/me')
export const getUsers  = () => req('/auth/users')
export const createUser = (d: UserIn) =>
  req('/auth/users', { method: 'POST', body: JSON.stringify(d) })
export const updateUser = (id: number, d: Partial<UserIn>) =>
  req(`/auth/users/${id}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteUser = (id: number) =>
  req(`/auth/users/${id}`, { method: 'DELETE' })

// ── Stats generales ──────────────────────────────────────────────
export const getStats = () => req('/stats')

// ── Conversaciones ───────────────────────────────────────────────
export const getConversations       = () => req('/conversations')
export const getConversationHistory = (phone: string) =>
  req(`/conversations/${encodeURIComponent(phone)}`)
export const sendManualReply = (phone: string, message: string, pause_minutes = 45) =>
  req(`/conversations/${encodeURIComponent(phone)}/reply`, {
    method: 'POST',
    body: JSON.stringify({ message, pause_minutes }),
  })
export const resumeBot = (phone: string) =>
  req(`/conversations/${encodeURIComponent(phone)}/resume-bot`, { method: 'POST' })

// ── Tiendas ──────────────────────────────────────────────────────
export const getStores   = ()                            => req('/stores')
export const createStore = (d: StorePayload)             => req('/stores', { method: 'POST', body: JSON.stringify(d) })
export const updateStore = (i: number, d: StorePayload)  => req(`/stores/${i}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteStore = (i: number)                   => req(`/stores/${i}`, { method: 'DELETE' })
export const exportStores = ()          => downloadFile('/stores/export', 'locales.csv')
export const importStores = (file: File) => uploadFile('/stores/import', file)

// ── Eventos ──────────────────────────────────────────────────────
export const getEvents   = ()                            => req('/events')
export const createEvent = (d: EventPayload)             => req('/events', { method: 'POST', body: JSON.stringify(d) })
export const updateEvent = (i: number, d: EventPayload)  => req(`/events/${i}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteEvent = (i: number)                   => req(`/events/${i}`, { method: 'DELETE' })
export const exportEvents = ()          => downloadFile('/events/export', 'eventos.csv')
export const importEvents = (file: File) => uploadFile('/events/import', file)

// ── Marketing (promociones de tiendas, del cine, o generales) ────
export const getMarketing    = ()                               => req('/marketing')
export const createMarketing = (d: MarketingPayload)            => req('/marketing', { method: 'POST', body: JSON.stringify(d) })
export const updateMarketing = (i: number, d: MarketingPayload) => req(`/marketing/${i}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteMarketing = (i: number)                      => req(`/marketing/${i}`, { method: 'DELETE' })

// ── Cartelera de Cine (funciones/estrenos ligadas a la tienda del Cine) ──
export const getCineFunciones    = (storeId: number)                  => req(`/cine-funciones?store_id=${storeId}`)
export const createCineFuncion   = (d: CineFuncionPayload)            => req('/cine-funciones', { method: 'POST', body: JSON.stringify(d) })
export const updateCineFuncion   = (i: number, d: CineFuncionPayload) => req(`/cine-funciones/${i}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteCineFuncion   = (i: number)                        => req(`/cine-funciones/${i}`, { method: 'DELETE' })

// ── Base de Conocimiento ────────────────────────────────────────────
export interface KnowledgeEntry { id?: number; title: string; content: string; photo_url?: string; active?: boolean; photos?: EntityPhoto[] }
export const getKnowledge    = ()                              => req('/knowledge')
export const createKnowledge = (d: KnowledgeEntry)              => req('/knowledge', { method: 'POST', body: JSON.stringify(d) })
export const updateKnowledge = (id: number, d: KnowledgeEntry)  => req(`/knowledge/${id}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteKnowledge = (id: number)                     => req(`/knowledge/${id}`, { method: 'DELETE' })
export const exportKnowledge = ()          => downloadFile('/knowledge/export', 'base_de_conocimiento.csv')
export const importKnowledge = (file: File) => uploadFile('/knowledge/import', file)

// ── Zonas (navegación QR indoor) ────────────────────────────────────
export interface Zone { id?: number; code: string; floor: string; description: string; photo_url?: string; qr_link?: string; photos?: EntityPhoto[] }
export const getZones      = ()                        => req('/zones')
export const createZone    = (d: Zone)                  => req('/zones', { method: 'POST', body: JSON.stringify(d) })
export const updateZone    = (id: number, d: Zone)      => req(`/zones/${id}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteZone    = (id: number)               => req(`/zones/${id}`, { method: 'DELETE' })
export const getZoneStats  = ()                         => req('/zones/stats')

// ── Info General del Mall ───────────────────────────────────────────
export interface MallInfo {
  id?: number | null; name: string; address: string
  general_schedule: string; phone: string; parking: string; wifi: string
  latitude?: string; longitude?: string
}
export const getMallInfo    = ()                 => req('/mall-info')
export const updateMallInfo = (d: MallInfo)      => req('/mall-info', { method: 'PUT', body: JSON.stringify(d) })

export interface InfoPoint { id?: number; name: string; floor: string; location: string }
export const getInfoPoints    = ()                            => req('/info-points')
export const createInfoPoint  = (d: InfoPoint)                 => req('/info-points', { method: 'POST', body: JSON.stringify(d) })
export const updateInfoPoint  = (id: number, d: InfoPoint)     => req(`/info-points/${id}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteInfoPoint  = (id: number)                   => req(`/info-points/${id}`, { method: 'DELETE' })

// ── Analytics ────────────────────────────────────────────────────
export const getAnalyticsSummary  = (days = 7) => req(`/analytics/summary`)
export const getAnalyticsHeatmap  = (days = 7) => req(`/analytics/heatmap?days=${days}`)
export const getTopStores         = (days = 7) => req(`/analytics/top-stores?days=${days}`)
export const getTopWords          = (days = 7) => req(`/analytics/top-words?days=${days}`)
export const getTopCategories     = (days = 7) => req(`/analytics/categories?days=${days}`)
export const getAnalyticsInsights = ()         => req(`/analytics/insights`)


// ── Transferencias de Domicilio (reemplaza el flujo viejo de pedidos) ──
export const getDeliveryTransferStats = () => req('/delivery-transfers/stats')
export const getDeliveryTransfers     = () => req('/delivery-transfers')

// ── Subida real de imágenes (Locales, Zonas, Eventos, Sorteos, Conocimiento) ──
export const uploadImage = async (file: File): Promise<string> => {
  const result = await uploadFile('/uploads/image', file)
  return result.url
}

// ── Galería de fotos — Tiendas (tabla dedicada: portada / carta / otra) ──
export interface StorePhoto { id?: number; store_id?: number; photo_url: string; label: string; label_display?: string }
export const getStorePhotos   = (storeId: number)                  => req(`/stores/${storeId}/photos`)
export const addStorePhoto    = (storeId: number, d: StorePhoto)   => req(`/stores/${storeId}/photos`, { method: 'POST', body: JSON.stringify(d) })
export const deleteStorePhoto = (storeId: number, photoId: number) => req(`/stores/${storeId}/photos/${photoId}`, { method: 'DELETE' })

// ── Galería de fotos genérica — Eventos, Sorteos, Conocimiento, Zonas ────
export interface EntityPhoto { id?: number; entity_type?: string; entity_id?: number; photo_url: string; label: string; label_display?: string }
export const getEntityPhotos   = (entityType: string, entityId: number)                  => req(`/photos/${entityType}/${entityId}`)
export const addEntityPhoto    = (entityType: string, entityId: number, d: EntityPhoto)  => req(`/photos/${entityType}/${entityId}`, { method: 'POST', body: JSON.stringify(d) })
export const deleteEntityPhoto = (entityType: string, entityId: number, photoId: number) => req(`/photos/${entityType}/${entityId}/${photoId}`, { method: 'DELETE' })

// ── Gestiones completas de domicilio (carta + datos + link personalizado) ──
export const getDeliveryManagementStats = () => req('/delivery-managements/stats')
export const getDeliveryManagements     = () => req('/delivery-managements')

// ── Sorteos y Campañas (distinto de Eventos) ────────────────────────
export interface Raffle {
  id?: number; name: string; prize: string; requirements: string
  end_date: string; location: string; description: string
  priority: number; photo_url?: string; active?: boolean; photos?: EntityPhoto[]
}
export const getRaffles      = ()                    => req('/raffles')
export const createRaffle    = (d: Raffle)            => req('/raffles', { method: 'POST', body: JSON.stringify(d) })
export const updateRaffle    = (id: number, d: Raffle) => req(`/raffles/${id}`, { method: 'PUT', body: JSON.stringify(d) })
export const toggleRaffle    = (id: number)           => req(`/raffles/${id}/toggle`, { method: 'PATCH' })
export const deleteRaffle    = (id: number)           => req(`/raffles/${id}`, { method: 'DELETE' })

// ── Domicilios / Pedidos (código viejo — ya no se usa en el panel,
//    se deja por si se necesita como referencia histórica) ─────────
export const getOrders         = ()              => req('/orders')
export const getActiveOrders   = ()              => req('/orders')
export const getAllOrders       = (limit = 100)  => req(`/orders/all?limit=${limit}`)
export const getOrderStats     = (): Promise<OrderStats> => req('/orders/stats')
export const getOrdersByStore  = (store: string) => req(`/orders/store/${encodeURIComponent(store)}`)
export const updateOrderStatus = (
  id: number,
  status: string,
  reason = '',
  deliveryTimeMinutes?: number,
  total?: number,
  storeMessage?: string,
) =>
  req(`/orders/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({
      status,
      reject_reason:         reason,
      delivery_time_minutes: deliveryTimeMinutes,
      total,
      store_message:         storeMessage,
    }),
  })

// ── Productos ────────────────────────────────────────────────────
export const getProducts   = (store: string)           => req(`/products/${encodeURIComponent(store)}`)
export const createProduct = (d: ProductPayload)       => req('/products', { method: 'POST', body: JSON.stringify(d) })
export const updateProduct = (id: number, d: ProductPayload) => req(`/products/${id}`, { method: 'PUT', body: JSON.stringify(d) })
export const deleteProduct = (id: number)              => req(`/products/${id}`, { method: 'DELETE' })
export const toggleProduct = (id: number)              => req(`/products/${id}/toggle`, { method: 'PATCH' })

// ── Perfilado ────────────────────────────────────────────────────
export const runProfiling = () => req('/run-profiling', { method: 'POST' })

// ── Types ─────────────────────────────────────────────────────────
export interface UserIn {
  username:   string
  full_name?: string
  password:   string
  role:       string
  store_name?: string
  store_type?: string
  store_id?:   string
  is_active?:  boolean
}
export interface StorePayload {
  id?: number; name: string; local_number: string; floor: string; category: string
  description: string; schedule: string
  phone: string; location_hint: string; tags: string; photo_url: string; extra_info: string
  photos?: StorePhoto[]
}
export interface EventPayload {
  id?: number; name: string; date: string; time: string
  location: string; description: string; priority: number; photo_url?: string; photos?: EntityPhoto[]
}
export interface MarketingPayload {
  id?: number; title: string; description: string
  store_id: number | null; store_name?: string
  priority: number; valid_until: string; active: boolean; photo_url?: string; photos?: EntityPhoto[]
}
export interface CineFuncionPayload {
  id?: number; store_id: number; title: string
  showtimes: string; description: string; is_premiere: boolean; active: boolean
}
export interface ProductPayload {
  store_name: string; name: string; description: string
  price: number; category: string; photo_url: string; active: boolean
}
export interface OrderStats {
  total_today:     number
  delivered_today: number
  pending_now:     number
  revenue_today:   number
  top_stores:      { store: string; total: number }[]
  avg_ratings:     { store: string; avg: number }[]
  hourly_chart:    { hora: string; pedidos: number }[]
}
export interface StatsData {
  total_messages: number; unique_users: number
  messages_today: number; messages_this_week: number
  total_stores: number; total_events: number
  daily_chart: { day: string; mensajes: number }[]
  hourly_chart: { hora: string; mensajes: number }[]
}
export interface ConvUser {
  phone: string; name: string; total: number; last_seen: string
  needs_human?: boolean; escalation_reason?: string | null; bot_paused?: boolean
}
export interface Order {
  id: number; order_number: string; client_phone: string; client_name: string
  store_name: string; status: string; total: number; subtotal: number
  delivery_fee: number; delivery_address: string; notes: string
  payment_method: string | null; delivery_time_minutes: number | null
  store_message: string | null
  items: OrderItem[]
  rating: { score: number; comment: string } | null
  created_at: string; delivered_at: string | null; reject_reason: string | null
}
export interface OrderItem {
  product_name: string; quantity: number; unit_price: number
  subtotal: number; notes: string
}
export interface Product {
  id: number; store_name: string; name: string; description: string
  price: number; category: string; photo_url: string; active: boolean
}
export interface AdminUser {
  id: number; username: string; full_name: string; role: string
  role_label: string; store_name: string | null; store_type: string | null
  store_id: string | null; is_active: boolean; created_at: string
}