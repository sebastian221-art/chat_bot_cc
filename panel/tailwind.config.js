// 📄 ARCHIVO: panel/tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg:           '#07090F',
        surface:      '#0D1117',
        card:         '#111720',
        border:       '#1C2333',
        accent:       '#3B82F6',
        'accent-glow':'rgba(59,130,246,0.15)',
        success:      '#10B981',
        warning:      '#F59E0B',
        danger:       '#EF4444',
        muted:        '#374151',
        text:         '#F0F4FF',
        'text-dim':   '#8B9BC4',
        'text-faint': '#4B5670',
      },
    },
  },
  plugins: [],
}