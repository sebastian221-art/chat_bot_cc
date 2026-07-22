// 📄 ARCHIVO: panel/app/layout.tsx
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Panel Admin — Mall El Puente',
  description: 'Panel de administración del chatbot del Centro Comercial El Puente',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  )
}