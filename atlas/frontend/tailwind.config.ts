import type { Config } from 'tailwindcss' 
 
export default { 
  content: ['./index.html', './src/**/*.{ts,tsx}'], 
  theme: { 
    extend: { 
      colors: { 
        atlas: { 
          bg:           '#0a0c0f', 
          surface:      '#0f1218', 
          surface2:     '#141820', 
          border:       '#1e2530', 
          'border-hi':  '#2a3545', 
          accent:       '#00d4ff', 
          long:         '#00ff9d', 
          short:        '#ff4d6d', 
          neutral:      '#ffd166', 
          'text-dim':   '#6a7d92', 
          'text-bright':'#e8f4ff', 
          text:         '#c8d8e8' 
        } 
      }, 
      fontFamily: { 
        mono: ['"IBM Plex Mono"', 'monospace'], 
        sans: ['"IBM Plex Sans"', 'sans-serif'] 
      } 
    } 
  }, 
  darkMode: 'class' 
} satisfies Config 
