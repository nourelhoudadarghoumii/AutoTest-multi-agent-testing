/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Engineering blues — primary brand scale
        cap: {
          50: '#F0F8FC',
          100: '#DCEFF9',
          200: '#BCE0F2',
          300: '#8FCBE9',
          400: '#4FAEDB',
          500: '#0070AD', // Primary brand blue
          600: '#005F92',
          700: '#0B4E78',
          800: '#103D5E',
          900: '#12304A',
          950: '#0B1F30',
        },
        // Bright accent — live activity, active states
        accent: {
          400: '#33B6E8',
          500: '#00A3E0',
          600: '#0086BD',
        },
        // Status scales
        success: {
          50: '#EFFAF3',
          100: '#D8F2E3',
          200: '#B4E4CB',
          400: '#4CC38A',
          500: '#2BA46B',
          600: '#218555',
          700: '#1A6A45',
        },
        warning: {
          50: '#FDF7EC',
          100: '#FAECD2',
          200: '#F4D9A5',
          400: '#E5A83C',
          500: '#D18F1F',
          600: '#A97318',
          700: '#855C15',
        },
        danger: {
          50: '#FCF1F1',
          100: '#F9DEDE',
          200: '#F2BCBC',
          400: '#E06B6B',
          500: '#CE3D3D',
          600: '#AC2E2E',
          700: '#8B2626',
        },
        slate2: {
          50: '#F7FAFC',
          100: '#EFF4F8',
          200: '#E2EAF1',
          300: '#CBD8E3',
          400: '#94A8BA',
          500: '#64798C',
          600: '#4B5E70',
          700: '#3A4A5A',
          800: '#2A3846',
          900: '#1C2733',
          950: '#0F1720',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      boxShadow: {
        'soft': '0 2px 10px rgba(11, 31, 48, 0.05)',
        'card': '0 1px 3px rgba(11, 31, 48, 0.07)',
        'glow': '0 0 0 1px rgba(0, 112, 173, 0.25), 0 0 20px rgba(0, 112, 173, 0.10)',
      },
    },
  },
  plugins: [],
}
